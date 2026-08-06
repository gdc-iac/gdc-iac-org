import axios from 'axios';

// 1. Cryptographically strong random string generator
function generateRandomString(length) {
    const array = new Uint8Array(length);
    window.crypto.getRandomValues(array);
    return Array.from(array, dec => ('0' + dec.toString(16)).slice(-2)).join('').substring(0, length);
}

// 2. SHA-256 Hashing using browser subtle-crypto APIs (zero external packages)
async function sha256(plain) {
    const encoder = new TextEncoder();
    const data = encoder.encode(plain);
    return window.crypto.subtle.digest('SHA-256', data);
}

// 3. Base64URL encoder
function base64urlencode(a) {
    let str = "";
    const bytes = new Uint8Array(a);
    const len = bytes.byteLength;
    for (let i = 0; i < len; i++) str += String.fromCharCode(bytes[i]);
    return btoa(str).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

async function generateCodeChallenge(v) {
    const hashed = await sha256(v);
    return base64urlencode(hashed);
}

// 4. Pure JS base64url JWT decoder for rendering user names & badges in the UI
export function decodeJwt(token) {
    try {
        const base64Url = token.split('.')[1];
        const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
        const jsonPayload = decodeURIComponent(window.atob(base64).split('').map(function(c) {
            return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
        }).join(''));
        return JSON.parse(jsonPayload);
    } catch (e) {
        return null;
    }
}

// 5. Dynamic redirect to Keycloak Authorization screen
export async function redirectToLogin(authority, clientId) {
    const verifier = generateRandomString(64);
    sessionStorage.setItem("oidc_verifier", verifier);
    const challenge = await generateCodeChallenge(verifier);
    const state = generateRandomString(16);
    sessionStorage.setItem("oidc_state", state);
    
    const redirectUri = window.location.origin;
    const authUrl = `${authority}/protocol/openid-connect/auth` +
        `?response_type=code` +
        `&client_id=${encodeURIComponent(clientId)}` +
        `&redirect_uri=${encodeURIComponent(redirectUri)}` +
        `&scope=openid%20profile%20roles` +
        `&code_challenge=${encodeURIComponent(challenge)}` +
        `&code_challenge_method=S256` +
        `&state=${encodeURIComponent(state)}`;
        
    window.location.href = authUrl;
}

// 6. Exchange Authorization Code for JWT Access Tokens (REST POST)
export async function exchangeCodeForTokens(authority, clientId, code, state) {
    const savedState = sessionStorage.getItem("oidc_state");
    if (state !== savedState) throw new Error("State validation mismatched");
    
    const verifier = sessionStorage.getItem("oidc_verifier");
    if (!verifier) throw new Error("Verification challenge code not found");
    
    const redirectUri = window.location.origin;
    const tokenUrl = `${authority}/protocol/openid-connect/token`;
    
    const params = new URLSearchParams();
    params.append("grant_type", "authorization_code");
    params.append("client_id", clientId);
    params.append("code", code);
    params.append("redirect_uri", redirectUri);
    params.append("code_verifier", verifier);
    
    const res = await axios.post(tokenUrl, params, {
        headers: { "Content-Type": "application/x-www-form-urlencoded" }
    });
    
    sessionStorage.removeItem("oidc_state");
    sessionStorage.removeItem("oidc_verifier");
    return res.data;
}
