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

package main

import (
	"bytes"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/binary"
	"encoding/json"
	"encoding/pem"
	"io"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"testing"
)

func TestToGDCKeyName(t *testing.T) {
	cases := []struct {
		in       string
		fallback string
		want     string
	}{
		{
			in:       "projects/iac-root/locations/zone1/keyRings/iac-root/cryptoKeys/vault-unseal-key",
			fallback: "",
			want:     "namespaces/iac-root/aeadKeys/vault-unseal-key",
		},
		{
			in:       "projects/my-gdc-project/locations/zone1/keyRings/vault-ring/cryptoKeys/vault-unseal-key",
			fallback: "",
			want:     "namespaces/my-gdc-project/aeadKeys/vault-unseal-key",
		},
		{
			in:       "namespaces/iac-root/aeadkeys/vault-unseal-key",
			fallback: "",
			want:     "namespaces/iac-root/aeadKeys/vault-unseal-key",
		},
		{
			in:       "invalid",
			fallback: "tenant-alpha",
			want:     "namespaces/tenant-alpha/aeadKeys/vault-unseal-key",
		},
	}
	for _, tc := range cases {
		got := toGDCKeyName(tc.in, tc.fallback)
		if got != tc.want {
			t.Errorf("toGDCKeyName(%q, %q) = %q; want %q", tc.in, tc.fallback, got, tc.want)
		}
	}
}

func makeGRPCFrame(proto []byte) []byte {
	f := make([]byte, 5+len(proto))
	f[0] = 0
	binary.BigEndian.PutUint32(f[1:5], uint32(len(proto)))
	copy(f[5:], proto)
	return f
}

func TestBridgeEncryptDecryptAndLoopbackGuard(t *testing.T) {
	var seenKMSKey string
	mockGDC := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		switch r.URL.Path {
		case "/authenticate":
			var req map[string]string
			_ = json.NewDecoder(r.Body).Decode(&req)
			if req["subject_token_type"] != "urn:k8s:params:oauth:token-type:serviceaccount" {
				t.Errorf("unexpected subject_token_type: %s", req["subject_token_type"])
			}
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(map[string]string{"access_token": "sts-token-123"})

		case "/goog.gdc.kms.v1.CryptoOperationsService/Encrypt":
			if r.Header.Get("Authorization") != "Bearer sts-token-123" {
				t.Errorf("missing STS Bearer token: %q", r.Header.Get("Authorization"))
			}
			raw, _ := io.ReadAll(r.Body)
			fields, _ := parseProtoFields(raw[5:])
			seenKMSKey = string(fields[1])
			var resp []byte
			resp = appendBytesField(resp, 2, append([]byte("ENC:"), fields[2]...))
			writeGRPCResponse(w, resp)

		case "/goog.gdc.kms.v1.CryptoOperationsService/Decrypt":
			raw, _ := io.ReadAll(r.Body)
			fields, _ := parseProtoFields(raw[5:])
			pt := bytes.TrimPrefix(fields[2], []byte("ENC:"))
			var resp []byte
			resp = appendBytesField(resp, 1, pt)
			writeGRPCResponse(w, resp)

		default:
			t.Fatalf("unexpected path: %s", r.URL.Path)
		}
	}))
	defer mockGDC.Close()

	priv, err := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if err != nil {
		t.Fatal(err)
	}
	pkcs8, err := x509.MarshalPKCS8PrivateKey(priv)
	if err != nil {
		t.Fatal(err)
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "PRIVATE KEY", Bytes: pkcs8})

	tmpDir := t.TempDir()
	saFile := filepath.Join(tmpDir, "vault-kms-sa.json")
	saData, _ := json.Marshal(saKeyFile{
		Project:      "iac-root",
		Name:         "vault-kms-sa",
		PrivateKeyID: "kid-001",
		PrivateKey:   string(pemBytes),
		TokenURI:     mockGDC.URL + "/authenticate",
	})
	if err := os.WriteFile(saFile, saData, 0600); err != nil {
		t.Fatal(err)
	}

	// Verify setupTLSAndCreds creates expected files.
	sharedDir := filepath.Join(tmpDir, "kms-bridge")
	if _, err := setupTLSAndCreds(sharedDir); err != nil {
		t.Fatalf("setupTLSAndCreds failed: %v", err)
	}
	for _, fn := range []string{"server.crt", "server.key", "ca-certificates.crt", "gcp-credentials.json"} {
		if _, err := os.Stat(filepath.Join(sharedDir, fn)); err != nil {
			t.Errorf("missing generated file %s: %v", fn, err)
		}
	}

	bs := &bridgeServer{
		saPath:         saFile,
		kmsEndpoint:    mockGDC.URL,
		defaultProject: "iac-root",
		hc:             mockGDC.Client(),
	}

	// 1. Non-loopback caller to /token must be rejected with 403 Forbidden.
	nonLoopReq := httptest.NewRequest("POST", "https://oauth2.googleapis.com/token", nil)
	nonLoopReq.RemoteAddr = "10.99.25.50:54321"
	nonLoopRec := httptest.NewRecorder()
	bs.ServeHTTP(nonLoopRec, nonLoopReq)
	if nonLoopRec.Code != http.StatusForbidden {
		t.Fatalf("expected 403 for non-loopback caller, got %d", nonLoopRec.Code)
	}

	// 2. /healthz succeeds even from kubelet pod IP.
	healthReq := httptest.NewRequest("GET", "http://10.99.25.10:18080/healthz", nil)
	healthReq.RemoteAddr = "10.99.25.1:41234"
	healthRec := httptest.NewRecorder()
	bs.ServeHTTP(healthRec, healthReq)
	if healthRec.Code != http.StatusOK {
		t.Fatalf("expected 200 on /healthz, got %d", healthRec.Code)
	}

	// 3. Loopback Encrypt -> Decrypt round-trip translates GCP resource URI to camelCase AEADKey URI.
	gcpKeyURI := "projects/iac-root/locations/zone1/keyRings/iac-root/cryptoKeys/vault-unseal-key"
	var encProto []byte
	encProto = appendBytesField(encProto, 1, []byte(gcpKeyURI))
	encProto = appendBytesField(encProto, 2, []byte("vault-master-key-32-bytes-secret"))

	encReq := httptest.NewRequest(
		"POST",
		"https://cloudkms.googleapis.com/google.cloud.kms.v1.KeyManagementService/Encrypt",
		bytes.NewReader(makeGRPCFrame(encProto)),
	)
	encReq.RemoteAddr = "127.0.0.1:45678"
	encRec := httptest.NewRecorder()
	bs.ServeHTTP(encRec, encReq)
	if encRec.Code != http.StatusOK || encRec.Header().Get("Grpc-Status") != "0" {
		t.Fatalf("Encrypt failed: code=%d grpc-status=%q", encRec.Code, encRec.Header().Get("Grpc-Status"))
	}
	if seenKMSKey != "namespaces/iac-root/aeadKeys/vault-unseal-key" {
		t.Fatalf("expected translated GDC KMS URI, got %q", seenKMSKey)
	}

	encOut, _ := parseProtoFields(encRec.Body.Bytes()[5:])
	ciphertext := encOut[2]

	var decProto []byte
	decProto = appendBytesField(decProto, 1, []byte(gcpKeyURI))
	decProto = appendBytesField(decProto, 2, ciphertext)

	decReq := httptest.NewRequest(
		"POST",
		"https://cloudkms.googleapis.com/google.cloud.kms.v1.KeyManagementService/Decrypt",
		bytes.NewReader(makeGRPCFrame(decProto)),
	)
	decReq.RemoteAddr = "127.0.0.1:45679"
	decRec := httptest.NewRecorder()
	bs.ServeHTTP(decRec, decReq)
	if decRec.Code != http.StatusOK || decRec.Header().Get("Grpc-Status") != "0" {
		t.Fatalf("Decrypt failed: code=%d grpc-status=%q", decRec.Code, decRec.Header().Get("Grpc-Status"))
	}
	decOut, _ := parseProtoFields(decRec.Body.Bytes()[5:])
	if string(decOut[1]) != "vault-master-key-32-bytes-secret" {
		t.Fatalf("Decrypt plaintext mismatch: got %q", string(decOut[1]))
	}
}
