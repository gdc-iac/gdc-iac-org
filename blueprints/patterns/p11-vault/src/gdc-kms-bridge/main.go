// Copyright 2026 Google LLC
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

// Package main implements gdc-kms-bridge, a zero-dependency local sidecar that
// bridges HashiCorp Vault's built-in `seal "gcpckms"` gRPC seal client to the
// Google Distributed Cloud air-gapped (GDCag) KMS CryptoOperationsService API
// authenticated via ES256 GDC STS token exchange.
package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"crypto/x509/pkix"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"io"
	"log"
	"math/big"
	"net"
	"net/http"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

const maxGRPCFrameBytes = 4 << 20 // 4 MiB max request/response payload

type saKeyFile struct {
	Project      string `json:"project"`
	Name         string `json:"name"`
	PrivateKeyID string `json:"private_key_id"`
	PrivateKey   string `json:"private_key"`
	TokenURI     string `json:"token_uri"`
}

type bridgeServer struct {
	saPath           string
	kmsEndpoint      string
	defaultProject   string
	allowNonLoopback bool
	hc               *http.Client

	mu          sync.Mutex
	cachedToken string
	tokenExpiry time.Time
}

func parseECPrivateKey(pemStr string) (*ecdsa.PrivateKey, error) {
	block, _ := pem.Decode([]byte(pemStr))
	if block == nil {
		return nil, fmt.Errorf("failed to decode PEM private_key")
	}
	if k, err := x509.ParseECPrivateKey(block.Bytes); err == nil {
		return k, nil
	}
	k2, err := x509.ParsePKCS8PrivateKey(block.Bytes)
	if err != nil {
		return nil, fmt.Errorf("parse EC private key failed: %w", err)
	}
	ecKey, ok := k2.(*ecdsa.PrivateKey)
	if !ok {
		return nil, fmt.Errorf("PKCS#8 private key is %T, expected *ecdsa.PrivateKey (ES256)", k2)
	}
	return ecKey, nil
}

func (b *bridgeServer) getSTSToken() (string, error) {
	b.mu.Lock()
	defer b.mu.Unlock()
	if b.cachedToken != "" && time.Now().Before(b.tokenExpiry) {
		return b.cachedToken, nil
	}
	raw, err := os.ReadFile(b.saPath)
	if err != nil {
		return "", fmt.Errorf("read SA key: %w", err)
	}
	var sa saKeyFile
	if err := json.Unmarshal(raw, &sa); err != nil {
		return "", fmt.Errorf("unmarshal SA key: %w", err)
	}
	if sa.Project == "" || sa.Name == "" || sa.TokenURI == "" {
		return "", fmt.Errorf("SA key missing required project, name, or token_uri fields")
	}
	ecKey, err := parseECPrivateKey(sa.PrivateKey)
	if err != nil {
		return "", err
	}

	hdr, _ := json.Marshal(map[string]string{
		"alg": "ES256",
		"kid": sa.PrivateKeyID,
		"typ": "JWT",
	})
	now := time.Now().Unix()
	sub := fmt.Sprintf("system:serviceaccount:%s:%s", sa.Project, sa.Name)
	pay, _ := json.Marshal(map[string]any{
		"aud": sa.TokenURI,
		"exp": now + 3600,
		"iat": now,
		"iss": sub,
		"sub": sub,
	})
	b64 := base64.RawURLEncoding.EncodeToString
	signingInput := b64(hdr) + "." + b64(pay)
	digest := sha256.Sum256([]byte(signingInput))
	r, s, err := ecdsa.Sign(rand.Reader, ecKey, digest[:])
	if err != nil {
		return "", err
	}
	curveBytes := (elliptic.P256().Params().BitSize + 7) / 8
	sig := make([]byte, 2*curveBytes)
	r.FillBytes(sig[:curveBytes])
	s.FillBytes(sig[curveBytes:])
	jwt := signingInput + "." + b64(sig)

	reqBody, _ := json.Marshal(map[string]string{
		"audience":             b.kmsEndpoint,
		"grant_type":           "urn:ietf:params:oauth:token-type:token-exchange",
		"requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
		"subject_token":        jwt,
		"subject_token_type":   "urn:k8s:params:oauth:token-type:serviceaccount",
	})
	resp, err := b.hc.Post(sa.TokenURI, "application/json", bytes.NewReader(reqBody))
	if err != nil {
		return "", fmt.Errorf("STS POST: %w", err)
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, maxGRPCFrameBytes))
	if err != nil {
		return "", fmt.Errorf("STS read body: %w", err)
	}
	if resp.StatusCode != http.StatusOK {
		return "", fmt.Errorf("STS status %d: %s", resp.StatusCode, string(body))
	}
	var out struct {
		AccessToken string `json:"access_token"`
	}
	if err := json.Unmarshal(body, &out); err != nil {
		return "", fmt.Errorf("STS json: %w", err)
	}
	if out.AccessToken == "" {
		return "", fmt.Errorf("STS response returned empty access_token")
	}
	b.cachedToken = out.AccessToken
	b.tokenExpiry = time.Now().Add(45 * time.Minute)
	return b.cachedToken, nil
}

func appendVarint(b []byte, v uint64) []byte {
	for v >= 0x80 {
		b = append(b, byte(v)|0x80)
		v >>= 7
	}
	return append(b, byte(v))
}

func appendBytesField(b []byte, fieldNum int, data []byte) []byte {
	if len(data) == 0 {
		return b
	}
	b = appendVarint(b, uint64((fieldNum<<3)|2))
	b = appendVarint(b, uint64(len(data)))
	return append(b, data...)
}

func parseProtoFields(b []byte) (map[int][]byte, map[int][][]byte) {
	single := map[int][]byte{}
	multi := map[int][][]byte{}
	i := 0
	for i < len(b) {
		tag, n := binary.Uvarint(b[i:])
		if n <= 0 {
			break
		}
		i += n
		fnum := int(tag >> 3)
		wtype := int(tag & 7)
		switch wtype {
		case 2:
			l, n2 := binary.Uvarint(b[i:])
			if n2 <= 0 || l > maxGRPCFrameBytes || i+n2+int(l) > len(b) {
				return single, multi
			}
			i += n2
			val := b[i : i+int(l)]
			single[fnum] = val
			multi[fnum] = append(multi[fnum], val)
			i += int(l)
		case 0:
			_, n2 := binary.Uvarint(b[i:])
			if n2 <= 0 {
				return single, multi
			}
			i += n2
		case 1:
			if i+8 > len(b) {
				return single, multi
			}
			i += 8
		case 5:
			if i+4 > len(b) {
				return single, multi
			}
			i += 4
		default:
			return single, multi
		}
	}
	return single, multi
}

// toGDCKeyName translates Vault's `seal "gcpckms"` resource URI
// (`projects/<project>/locations/<region>/keyRings/<ring>/cryptoKeys/<key>`)
// into the camelCase GDCag KMS resource URI (`namespaces/<ns>/aeadKeys/<key>`).
func toGDCKeyName(gcpName string, fallbackProject string) string {
	if strings.HasPrefix(gcpName, "namespaces/") {
		// Normalize accidental lowercase `/aeadkeys/` to required camelCase `/aeadKeys/`.
		return strings.Replace(gcpName, "/aeadkeys/", "/aeadKeys/", 1)
	}
	parts := strings.Split(gcpName, "/")
	var proj, kr, ck string
	for i := 0; i+1 < len(parts); i++ {
		switch parts[i] {
		case "projects":
			proj = parts[i+1]
		case "keyRings":
			kr = parts[i+1]
		case "cryptoKeys":
			ck = parts[i+1]
		}
	}
	ns := kr
	if ns == "" || ns == "vault-ring" {
		if proj != "" {
			ns = proj
		}
	}
	if ns != "" && ck != "" {
		return fmt.Sprintf("namespaces/%s/aeadKeys/%s", ns, ck)
	}
	if fallbackProject == "" {
		fallbackProject = "my-gdc-project"
	}
	if ck == "" {
		ck = "vault-unseal-key"
	}
	return fmt.Sprintf("namespaces/%s/aeadKeys/%s", fallbackProject, ck)
}

func (b *bridgeServer) callGDCKMS(method string, reqProto []byte) ([]byte, error) {
	tok, err := b.getSTSToken()
	if err != nil {
		return nil, err
	}
	frame := make([]byte, 5+len(reqProto))
	frame[0] = 0
	binary.BigEndian.PutUint32(frame[1:5], uint32(len(reqProto)))
	copy(frame[5:], reqProto)

	req, err := http.NewRequest("POST", strings.TrimRight(b.kmsEndpoint, "/")+method, bytes.NewReader(frame))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/grpc")
	req.Header.Set("Te", "trailers")
	req.Header.Set("Authorization", "Bearer "+tok)

	resp, err := b.hc.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	body, err := io.ReadAll(io.LimitReader(resp.Body, maxGRPCFrameBytes))
	if err != nil {
		return nil, err
	}
	if gs := resp.Trailer.Get("Grpc-Status"); gs != "" && gs != "0" {
		return nil, fmt.Errorf("gdc kms grpc error %s: %s", gs, resp.Trailer.Get("Grpc-Message"))
	}
	if gs := resp.Header.Get("Grpc-Status"); gs != "" && gs != "0" {
		return nil, fmt.Errorf("gdc kms header error %s: %s", gs, resp.Header.Get("Grpc-Message"))
	}
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("gdc kms http status %d: %s", resp.StatusCode, string(body))
	}
	if len(body) < 5 {
		return nil, fmt.Errorf("short gdc kms response (%d bytes)", len(body))
	}
	msgLen := binary.BigEndian.Uint32(body[1:5])
	if msgLen > maxGRPCFrameBytes || 5+int(msgLen) > len(body) {
		return nil, fmt.Errorf("truncated gdc kms response frame (declared=%d, have=%d)", msgLen, len(body)-5)
	}
	return body[5 : 5+int(msgLen)], nil
}

func writeGRPCResponse(w http.ResponseWriter, respProto []byte) {
	w.Header().Set("Content-Type", "application/grpc")
	w.Header().Set("Trailer", "Grpc-Status, Grpc-Message")
	w.WriteHeader(http.StatusOK)
	frame := make([]byte, 5+len(respProto))
	frame[0] = 0
	binary.BigEndian.PutUint32(frame[1:5], uint32(len(respProto)))
	copy(frame[5:], respProto)
	_, _ = w.Write(frame)
	if fl, ok := w.(http.Flusher); ok {
		fl.Flush()
	}
	w.Header().Set("Grpc-Status", "0")
	w.Header().Set("Grpc-Message", "")
}

func writeGRPCError(w http.ResponseWriter, msg string) {
	log.Printf("ERROR: %s", msg)
	w.Header().Set("Content-Type", "application/grpc")
	w.Header().Set("Trailer", "Grpc-Status, Grpc-Message")
	w.WriteHeader(http.StatusOK)
	w.Header().Set("Grpc-Status", "13")
	w.Header().Set("Grpc-Message", msg)
}

func isLoopbackRemote(remoteAddr string) bool {
	host, _, err := net.SplitHostPort(remoteAddr)
	if err != nil {
		host = remoteAddr
	}
	ip := net.ParseIP(host)
	return ip != nil && ip.IsLoopback()
}

func (b *bridgeServer) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path == "/healthz" {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write([]byte(`{"status":"ok"}`))
		return
	}

	if !b.allowNonLoopback && !isLoopbackRemote(r.RemoteAddr) {
		http.Error(w, "forbidden: loopback clients only", http.StatusForbidden)
		return
	}

	if r.URL.Path == "/token" {
		tok, err := b.getSTSToken()
		if err != nil {
			http.Error(w, err.Error(), http.StatusInternalServerError)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]any{
			"access_token": tok,
			"token_type":   "Bearer",
			"expires_in":   3600,
		})
		return
	}

	body, err := io.ReadAll(io.LimitReader(r.Body, maxGRPCFrameBytes))
	if err != nil || len(body) < 5 {
		writeGRPCError(w, "invalid grpc request frame")
		return
	}
	msgLen := binary.BigEndian.Uint32(body[1:5])
	if msgLen > maxGRPCFrameBytes || 5+int(msgLen) > len(body) {
		writeGRPCError(w, "truncated grpc frame")
		return
	}
	reqProto := body[5 : 5+int(msgLen)]
	single, multi := parseProtoFields(reqProto)

	switch r.URL.Path {
	case "/google.cloud.kms.v1.KeyManagementService/GetCryptoKey":
		var out []byte
		out = appendBytesField(out, 1, single[1])
		writeGRPCResponse(w, out)

	case "/google.iam.v1.IAMPolicy/TestIamPermissions":
		var out []byte
		for _, perm := range multi[2] {
			out = appendBytesField(out, 1, perm)
		}
		writeGRPCResponse(w, out)

	case "/google.cloud.kms.v1.KeyManagementService/Encrypt":
		origName := string(single[1])
		gdcName := toGDCKeyName(origName, b.defaultProject)
		var gdcReq []byte
		gdcReq = appendBytesField(gdcReq, 1, []byte(gdcName))
		gdcReq = appendBytesField(gdcReq, 2, single[2])
		gdcReq = appendBytesField(gdcReq, 3, single[3])

		gdcResp, err := b.callGDCKMS("/goog.gdc.kms.v1.CryptoOperationsService/Encrypt", gdcReq)
		if err != nil {
			writeGRPCError(w, err.Error())
			return
		}
		respFields, _ := parseProtoFields(gdcResp)
		var out []byte
		out = appendBytesField(out, 1, []byte(origName))
		out = appendBytesField(out, 2, respFields[2])
		log.Printf("GDCag KMS Encrypt succeeded for %s -> %s (ciphertext=%d bytes)", origName, gdcName, len(respFields[2]))
		writeGRPCResponse(w, out)

	case "/google.cloud.kms.v1.KeyManagementService/Decrypt":
		origName := string(single[1])
		gdcName := toGDCKeyName(origName, b.defaultProject)
		var gdcReq []byte
		gdcReq = appendBytesField(gdcReq, 1, []byte(gdcName))
		gdcReq = appendBytesField(gdcReq, 2, single[2])
		gdcReq = appendBytesField(gdcReq, 3, single[3])

		gdcResp, err := b.callGDCKMS("/goog.gdc.kms.v1.CryptoOperationsService/Decrypt", gdcReq)
		if err != nil {
			writeGRPCError(w, err.Error())
			return
		}
		respFields, _ := parseProtoFields(gdcResp)
		var out []byte
		out = appendBytesField(out, 1, respFields[1])
		log.Printf("GDCag KMS Decrypt succeeded for %s -> %s (plaintext=%d bytes)", origName, gdcName, len(respFields[1]))
		writeGRPCResponse(w, out)

	default:
		log.Printf("Unhandled gRPC method: %s", r.URL.Path)
		writeGRPCResponse(w, nil)
	}
}

func setupTLSAndCreds(tlsDir string) (tls.Certificate, error) {
	if err := os.MkdirAll(tlsDir, 0755); err != nil {
		return tls.Certificate{}, err
	}
	certPath := filepath.Join(tlsDir, "server.crt")
	keyPath := filepath.Join(tlsDir, "server.key")
	if _, err := os.Stat(certPath); err == nil {
		if _, err2 := os.Stat(keyPath); err2 == nil {
			return tls.LoadX509KeyPair(certPath, keyPath)
		}
	}
	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		return tls.Certificate{}, err
	}
	tmpl := x509.Certificate{
		SerialNumber:          big.NewInt(1),
		Subject:               pkix.Name{CommonName: "cloudkms.googleapis.com"},
		NotBefore:             time.Now().Add(-1 * time.Hour),
		NotAfter:              time.Now().Add(10 * 365 * 24 * time.Hour),
		KeyUsage:              x509.KeyUsageDigitalSignature | x509.KeyUsageKeyEncipherment | x509.KeyUsageCertSign,
		ExtKeyUsage:           []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth},
		BasicConstraintsValid: true,
		IsCA:                  true,
		DNSNames:              []string{"cloudkms.googleapis.com", "oauth2.googleapis.com", "localhost"},
		IPAddresses:           []net.IP{net.ParseIP("127.0.0.1")},
	}
	der, err := x509.CreateCertificate(rand.Reader, &tmpl, &tmpl, &priv.PublicKey, priv)
	if err != nil {
		return tls.Certificate{}, err
	}
	certPEM := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	privBytes, err := x509.MarshalECPrivateKey(priv)
	if err != nil {
		return tls.Certificate{}, err
	}
	keyPEM := pem.EncodeToMemory(&pem.Block{Type: "EC PRIVATE KEY", Bytes: privBytes})

	if err := os.WriteFile(certPath, certPEM, 0644); err != nil {
		return tls.Certificate{}, err
	}
	if err := os.WriteFile(keyPath, keyPEM, 0600); err != nil {
		return tls.Certificate{}, err
	}

	var combined bytes.Buffer
	if sysCA, err := os.ReadFile("/etc/ssl/certs/ca-certificates.crt"); err == nil {
		combined.Write(sysCA)
		combined.WriteByte('\n')
	}
	combined.Write(certPEM)
	if err := os.WriteFile(filepath.Join(tlsDir, "ca-certificates.crt"), combined.Bytes(), 0644); err != nil {
		return tls.Certificate{}, err
	}

	credsJSON := `{
  "type": "authorized_user",
  "client_id": "vault-kms-sa",
  "client_secret": "gdc-kms",
  "refresh_token": "gdc-kms",
  "token_uri": "https://oauth2.googleapis.com/token"
}
`
	if err := os.WriteFile(filepath.Join(tlsDir, "gcp-credentials.json"), []byte(credsJSON), 0644); err != nil {
		return tls.Certificate{}, err
	}
	return tls.X509KeyPair(certPEM, keyPEM)
}

func buildTLSClientConfig() *tls.Config {
	cfg := &tls.Config{
		MinVersion:       tls.VersionTLS12,
		CurvePreferences: []tls.CurveID{tls.X25519, tls.CurveP256},
		NextProtos:       []string{"h2", "http/1.1"},
	}
	caFile := os.Getenv("GDC_CA_CERT_FILE")
	if caFile != "" {
		if pemBytes, err := os.ReadFile(caFile); err == nil {
			pool, err := x509.SystemCertPool()
			if err != nil || pool == nil {
				pool = x509.NewCertPool()
			}
			if pool.AppendCertsFromPEM(pemBytes) {
				cfg.RootCAs = pool
				cfg.InsecureSkipVerify = strings.EqualFold(os.Getenv("GDC_INSECURE_SKIP_VERIFY"), "true")
				return cfg
			}
		}
		log.Printf("WARN: could not load GDC_CA_CERT_FILE=%s; falling back to default TLS verification setting", caFile)
	}
	skipEnv := os.Getenv("GDC_INSECURE_SKIP_VERIFY")
	if skipEnv == "" {
		// Default true when no GDC org CA bundle is mounted into the sidecar.
		cfg.InsecureSkipVerify = true
	} else {
		cfg.InsecureSkipVerify = strings.EqualFold(skipEnv, "true")
	}
	return cfg
}

func main() {
	saPath := os.Getenv("GDC_SA_KEY_FILE")
	if saPath == "" {
		saPath = "/vault/userconfig/gdc-kms-sa/vault-kms-sa.json"
	}
	kmsEndpoint := os.Getenv("GDC_KMS_ENDPOINT")
	if kmsEndpoint == "" {
		kmsEndpoint = "https://kms.org-12345.zone1.google.gdch.test"
	}
	tlsDir := os.Getenv("GDC_BRIDGE_SHARED_DIR")
	if tlsDir == "" {
		tlsDir = "/vault/kms-bridge"
	}
	listenAddr := os.Getenv("GDC_BRIDGE_LISTEN")
	if listenAddr == "" {
		listenAddr = "127.0.0.1:443"
	}
	healthAddr := os.Getenv("GDC_BRIDGE_HEALTH_LISTEN")
	if healthAddr == "" {
		healthAddr = "0.0.0.0:18080"
	}
	defaultProj := os.Getenv("GOOGLE_PROJECT")

	cert, err := setupTLSAndCreds(tlsDir)
	if err != nil {
		log.Fatalf("setupTLSAndCreds: %v", err)
	}
	if os.Getenv("INIT_ONLY") == "true" {
		log.Printf("Initialized TLS & credentials in %s", tlsDir)
		return
	}

	tr := &http.Transport{
		ForceAttemptHTTP2: true,
		TLSClientConfig:   buildTLSClientConfig(),
	}
	bs := &bridgeServer{
		saPath:           saPath,
		kmsEndpoint:      kmsEndpoint,
		defaultProject:   defaultProj,
		allowNonLoopback: strings.EqualFold(os.Getenv("GDC_ALLOW_NON_LOOPBACK"), "true"),
		hc:               &http.Client{Transport: tr, Timeout: 15 * time.Second},
	}

	ln, err := net.Listen("tcp", listenAddr)
	if err != nil {
		log.Fatalf("listen %s: %v", listenAddr, err)
	}

	if healthAddr != "off" && healthAddr != "disabled" {
		healthMux := http.NewServeMux()
		healthMux.HandleFunc("/healthz", func(w http.ResponseWriter, _ *http.Request) {
			w.Header().Set("Content-Type", "application/json")
			w.WriteHeader(http.StatusOK)
			_, _ = w.Write([]byte(`{"status":"ok"}`))
		})
		healthSrv := &http.Server{
			Addr:              healthAddr,
			Handler:           healthMux,
			ReadHeaderTimeout: 5 * time.Second,
		}
		go func() {
			log.Printf("gdc-kms-bridge health probe listening on %s/healthz", healthAddr)
			if herr := healthSrv.ListenAndServe(); herr != nil && herr != http.ErrServerClosed {
				log.Printf("WARN: health server exited: %v", herr)
			}
		}()
	}

	srv := &http.Server{
		Addr:              listenAddr,
		Handler:           bs,
		ReadHeaderTimeout: 10 * time.Second,
		TLSConfig: &tls.Config{
			MinVersion:   tls.VersionTLS12,
			Certificates: []tls.Certificate{cert},
			NextProtos:   []string{"h2", "http/1.1"},
		},
	}
	log.Printf("gdc-kms-bridge listening on %s -> %s", listenAddr, kmsEndpoint)
	log.Fatal(srv.Serve(tls.NewListener(ln, srv.TLSConfig)))
}
