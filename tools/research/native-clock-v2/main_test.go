package main

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"crypto/sha512"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"os"
	"reflect"
	"testing"
	"time"

	"github.com/cloudflare/roughtime/protocol"
)

// All signing keys in this file are deterministically generated SOFTWARE_ONLY
// controls. They are not keys of any external issuer.
type softwareExchange struct{ Request, Response, PublicKey []byte }

func softwareKey(label string) ed25519.PrivateKey {
	seed := sha256.Sum256([]byte("SOFTWARE_ONLY native-clock-v2 " + label))
	return ed25519.NewKeyFromSeed(seed[:])
}

func signedSoftwareExchange(t *testing.T, ver protocol.Version, midpoint int64, radius time.Duration, blind, previous []byte) softwareExchange {
	t.Helper()
	root, online := softwareKey("root"), softwareKey("online")
	pub := root.Public().(ed25519.PublicKey)
	_, _, req, err := protocol.CreateRequest([]protocol.Version{ver}, bytes.NewReader(blind), previous, pub)
	if err != nil {
		t.Fatal(err)
	}
	parsed, err := protocol.ParseRequest(req)
	if err != nil {
		t.Fatal(err)
	}
	cert, err := protocol.NewCertificate(time.Unix(1699999000, 0), time.Unix(1700001000, 0), online, root)
	if err != nil {
		t.Fatal(err)
	}
	replies, err := protocol.CreateReplies(ver, []protocol.Request{*parsed}, time.Unix(midpoint, 0), radius, cert)
	if err != nil {
		t.Fatal(err)
	}
	return softwareExchange{req, replies[0], pub}
}

func call(t *testing.T, fields map[string]any) (map[string]any, error) {
	t.Helper()
	in, err := json.Marshal(fields)
	if err != nil {
		t.Fatal(err)
	}
	var out bytes.Buffer
	err = run(bytes.NewReader(in), &out)
	if err != nil {
		if out.Len() != 0 {
			t.Fatalf("error leaked stdout diagnostics: %q", out.String())
		}
		return nil, err
	}
	var value map[string]any
	if err := json.Unmarshal(out.Bytes(), &value); err != nil {
		t.Fatal(err)
	}
	return value, nil
}

func verifyFields(x softwareExchange) map[string]any {
	return map[string]any{"op": "verify", "request_b64": b64(x.Request), "response_b64": b64(x.Response), "public_key_b64": b64(x.PublicKey)}
}
func b64(b []byte) string { return base64.StdEncoding.EncodeToString(b) }
func tag(s string) uint32 { return binary.LittleEndian.Uint32([]byte(s)) }
func mustDecode(t *testing.T, framed []byte) map[uint32][]byte {
	t.Helper()
	m, err := protocol.Decode(framed[12:])
	if err != nil {
		t.Fatal(err)
	}
	return m
}
func reframe(t *testing.T, m map[uint32][]byte) []byte {
	t.Helper()
	body, err := protocol.Encode(m)
	if err != nil {
		t.Fatal(err)
	}
	out := append([]byte("ROUGHTIM"), make([]byte, 4)...)
	binary.LittleEndian.PutUint32(out[8:], uint32(len(body)))
	return append(out, body...)
}

func TestRequestUsesSuppliedBlindAndOnlyDraft08(t *testing.T) {
	blind := make([]byte, 32)
	for i := range blind {
		blind[i] = byte(i)
	}
	pub := softwareKey("root").Public().(ed25519.PublicKey)
	out, err := call(t, map[string]any{"op": "request", "previous_reply_b64": b64([]byte("SOFTWARE_ONLY previous reply")), "blind_b64": b64(blind), "public_key_b64": b64(pub)})
	if err != nil {
		t.Fatalf("request unavailable: %v", err)
	}
	if len(out) != 2 {
		t.Fatalf("request must contain exactly two original fields: %v", out)
	}
	if out["nonce_b64"] != "LgFOPpYRMbLRWPA8zogzSWjjcT3J8ezGzAuoWv9SSaQ=" {
		t.Fatalf("wrong chained nonce: %v", out["nonce_b64"])
	}
	req, err := base64.StdEncoding.DecodeString(out["request_b64"].(string))
	if err != nil {
		t.Fatal(err)
	}
	if !bytes.Equal(req[:8], []byte("ROUGHTIM")) || int(binary.LittleEndian.Uint32(req[8:12])) != len(req)-12 {
		t.Fatal("request not exactly IETF framed")
	}
	msg := mustDecode(t, req)
	if !bytes.Equal(msg[tag("VER\x00")], []byte{8, 0, 0, 128}) {
		t.Fatalf("advertised another version: %x", msg[tag("VER\x00")])
	}
	if b64(msg[tag("NONC")]) != out["nonce_b64"] {
		t.Fatal("request differs from returned nonce")
	}
}

func TestSignedSoftwarePacketReportsSecondsOnly(t *testing.T) {
	x := signedSoftwareExchange(t, protocol.VersionDraft08, 1700000000, 3*time.Second, bytes.Repeat([]byte{9}, 32), nil)
	out, err := call(t, verifyFields(x))
	if err != nil {
		t.Fatalf("signed positive rejected: %v", err)
	}
	if len(out) != 3 || out["protocol"] != "draft-ietf-ntp-roughtime-08" || out["midpoint_unix_s"] != float64(1700000000) || out["radius_s"] != float64(3) {
		t.Fatalf("wrong diagnostic schema/units: %v", out)
	}
}

func TestRejectsPacketSubstitutions(t *testing.T) {
	original := signedSoftwareExchange(t, protocol.VersionDraft08, 1700000000, 3*time.Second, bytes.Repeat([]byte{9}, 32), nil)
	clone := func() softwareExchange {
		return softwareExchange{append([]byte(nil), original.Request...), append([]byte(nil), original.Response...), append([]byte(nil), original.PublicKey...)}
	}
	mutations := map[string]func(softwareExchange) softwareExchange{
		"unframed-response":                 func(x softwareExchange) softwareExchange { x.Response = x.Response[12:]; return x },
		"unframed-request":                  func(x softwareExchange) softwareExchange { x.Request = x.Request[12:]; return x },
		"wrong-response-frame-length":       func(x softwareExchange) softwareExchange { x.Response[8] ^= 4; return x },
		"wrong-request-frame-length":        func(x softwareExchange) softwareExchange { x.Request[8] ^= 4; return x },
		"response-frame-magic-substitution": func(x softwareExchange) softwareExchange { x.Response[0] = 'X'; return x },
		"request-frame-magic-substitution":  func(x softwareExchange) softwareExchange { x.Request[0] = 'X'; return x },
		"unused-index-bit": func(x softwareExchange) softwareExchange {
			m := mustDecode(t, x.Response)
			m[tag("INDX")] = []byte{1, 0, 0, 0}
			x.Response = reframe(t, m)
			return x
		},
		"request-advertises-draft11": func(x softwareExchange) softwareExchange {
			m := mustDecode(t, x.Request)
			m[tag("VER\x00")] = []byte{11, 0, 0, 128}
			x.Request = reframe(t, m)
			return x
		},
		"request-advertises-extra-version": func(x softwareExchange) softwareExchange {
			m := mustDecode(t, x.Request)
			m[tag("VER\x00")] = []byte{8, 0, 0, 128, 11, 0, 0, 128}
			x.Request = reframe(t, m)
			return x
		},
		"response-selects-draft11": func(x softwareExchange) softwareExchange {
			m := mustDecode(t, x.Response)
			m[tag("VER\x00")] = []byte{11, 0, 0, 128}
			x.Response = reframe(t, m)
			return x
		},
		"wrong-request-nonce": func(x softwareExchange) softwareExchange {
			m := mustDecode(t, x.Request)
			m[tag("NONC")][0] ^= 1
			x.Request = reframe(t, m)
			return x
		},
		"wrong-response-nonce": func(x softwareExchange) softwareExchange {
			m := mustDecode(t, x.Response)
			m[tag("NONC")][0] ^= 1
			x.Response = reframe(t, m)
			return x
		},
		"wrong-public-key": func(x softwareExchange) softwareExchange { x.PublicKey[0] ^= 1; return x },
		"short-public-key": func(x softwareExchange) softwareExchange { x.PublicKey = x.PublicKey[:31]; return x },
		"duplicate-response-tag": func(x softwareExchange) softwareExchange {
			n := int(binary.LittleEndian.Uint32(x.Response[12:16]))
			at := 12 + 4*n
			copy(x.Response[at+4:at+8], x.Response[at:at+4])
			return x
		},
		"duplicate-request-tag": func(x softwareExchange) softwareExchange {
			n := int(binary.LittleEndian.Uint32(x.Request[12:16]))
			at := 12 + 4*n
			copy(x.Request[at+4:at+8], x.Request[at:at+4])
			return x
		},
		"wrong-response-context": func(x softwareExchange) softwareExchange {
			m := mustDecode(t, x.Response)
			m[tag("SIG\x00")] = ed25519.Sign(softwareKey("online"), append([]byte("SOFTWARE_ONLY wrong context"), m[tag("SREP")]...))
			x.Response = reframe(t, m)
			return x
		},
		"wrong-delegation-context": func(x softwareExchange) softwareExchange {
			m := mustDecode(t, x.Response)
			c, err := protocol.Decode(m[tag("CERT")])
			if err != nil {
				t.Fatal(err)
			}
			c[tag("SIG\x00")] = ed25519.Sign(softwareKey("root"), append([]byte("SOFTWARE_ONLY wrong context"), c[tag("DELE")]...))
			m[tag("CERT")], err = protocol.Encode(c)
			if err != nil {
				t.Fatal(err)
			}
			x.Response = reframe(t, m)
			return x
		},
		"delegation-outside-midpoint": func(x softwareExchange) softwareExchange {
			m := mustDecode(t, x.Response)
			c, err := protocol.Decode(m[tag("CERT")])
			if err != nil {
				t.Fatal(err)
			}
			d, err := protocol.Decode(c[tag("DELE")])
			if err != nil {
				t.Fatal(err)
			}
			binary.LittleEndian.PutUint64(d[tag("MINT")], 1700000001)
			c[tag("DELE")], err = protocol.Encode(d)
			if err != nil {
				t.Fatal(err)
			}
			c[tag("SIG\x00")] = ed25519.Sign(softwareKey("root"), append([]byte("RoughTime v1 delegation signature--\x00"), c[tag("DELE")]...))
			m[tag("CERT")], err = protocol.Encode(c)
			if err != nil {
				t.Fatal(err)
			}
			x.Response = reframe(t, m)
			return x
		},
		"trailing-response-data": func(x softwareExchange) softwareExchange { x.Response = append(x.Response, 0, 0, 0, 0); return x },
	}
	for name, mutate := range mutations {
		t.Run(name, func(t *testing.T) {
			_, err := call(t, verifyFields(mutate(clone())))
			if err == nil {
				t.Fatal("substituted original packet accepted")
			}
		})
	}
}

func TestRejectsNonProtocolAndMalformedInputs(t *testing.T) {
	pub := b64(softwareKey("root").Public().(ed25519.PublicKey))
	cases := map[string]map[string]any{
		"network-operation":     {"op": "udp", "public_key_b64": pub},
		"caller-authority-flag": {"op": "request", "public_key_b64": pub, "blind_b64": b64(make([]byte, 32)), "native_authority": "VALID"},
		"short-blind":           {"op": "request", "public_key_b64": pub, "blind_b64": b64(make([]byte, 31))},
		"long-blind":            {"op": "request", "public_key_b64": pub, "blind_b64": b64(make([]byte, 33))},
		"invalid-base64":        {"op": "verify", "public_key_b64": pub, "request_b64": "%", "response_b64": "%"},
	}
	for name, fields := range cases {
		t.Run(name, func(t *testing.T) {
			if _, err := call(t, fields); err == nil {
				t.Fatal("malformed input accepted")
			}
		})
	}
}

func TestNonzeroConsumedMerkleIndexRemainsAccepted(t *testing.T) {
	root, online := softwareKey("root"), softwareKey("online")
	pub := root.Public().(ed25519.PublicKey)
	var requests []protocol.Request
	var packets [][]byte
	for i := 0; i < 3; i++ {
		_, _, packet, err := protocol.CreateRequest([]protocol.Version{protocol.VersionDraft08}, bytes.NewReader(bytes.Repeat([]byte{byte(i + 1)}, 32)), nil, pub)
		if err != nil {
			t.Fatal(err)
		}
		parsed, err := protocol.ParseRequest(packet)
		if err != nil {
			t.Fatal(err)
		}
		requests = append(requests, *parsed)
		packets = append(packets, packet)
	}
	cert, err := protocol.NewCertificate(time.Unix(1699999000, 0), time.Unix(1700001000, 0), online, root)
	if err != nil {
		t.Fatal(err)
	}
	replies, err := protocol.CreateReplies(protocol.VersionDraft08, requests, time.Unix(1700000000, 0), 3*time.Second, cert)
	if err != nil {
		t.Fatal(err)
	}
	for i, reply := range replies {
		out, err := call(t, verifyFields(softwareExchange{packets[i], reply, pub}))
		if err != nil {
			t.Fatalf("real Merkle index %d rejected: %v", i, err)
		}
		if out["midpoint_unix_s"] != float64(1700000000) {
			t.Fatal("wrong signed time")
		}
	}
}

// fixtureOriginals is a TEST-ONLY local signing generator. The production CLI
// has only request and verify and cannot sign or generate issuer fixtures.
func fixtureOriginals(t *testing.T) map[string]any {
	t.Helper()
	const slab = `{"acquisition_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","pairs":[{"clock_domain_id":"SOFTWARE_ONLY-clock-1","mono_after_ns":110,"mono_before_ns":100,"sequence":1,"utc_at":"2026-10-05T00:00:00+00:00"},{"clock_domain_id":"SOFTWARE_ONLY-clock-1","mono_after_ns":130,"mono_before_ns":120,"sequence":2,"utc_at":"2026-10-05T00:00:00+00:00"}],"schema_version":"native.clock.causal-slab.v2"}`
	commitmentA := sha256.Sum256([]byte("SOFTWARE_ONLY causal-before public commitment"))
	commitmentB := sha256.Sum256([]byte(slab))
	sourceA, sourceB := bytes.Repeat([]byte{10}, 32), bytes.Repeat([]byte{11}, 32)
	effective := func(source, commitment []byte) []byte {
		h := sha512.New()
		h.Write([]byte("BIGsmall native-clock-v2 commitment\x00"))
		h.Write(source)
		h.Write(commitment)
		return h.Sum(nil)[:32]
	}
	effectiveA, effectiveB := effective(sourceA, commitmentA[:]), effective(sourceB, commitmentB[:])
	a := signedSoftwareExchange(t, protocol.VersionDraft08, 1700000000, time.Second, effectiveA, nil)
	b := signedSoftwareExchange(t, protocol.VersionDraft08, 1700000002, time.Second, effectiveB, a.Response)
	exchange := func(id string, x softwareExchange, source, effective, commitment, previous []byte, base int64) map[string]any {
		return map[string]any{
			"clock_domain_id": "SOFTWARE_ONLY-clock-1", "exchange_id": id,
			"request_b64": b64(x.Request), "response_b64": b64(x.Response), "public_key_b64": b64(x.PublicKey),
			"commitment_b64": b64(commitment), "previous_reply_b64": b64(previous), "source_blind_b64": b64(source), "effective_blind_b64": b64(effective),
			"send_before_ns": base, "send_after_ns": base + 1, "receive_before_ns": base + 2, "receive_after_ns": base + 3, "verified_before_ns": base + 4, "verified_after_ns": base + 5,
		}
	}
	msg := mustDecode(t, a.Request)
	return map[string]any{
		"scope": "SOFTWARE_ONLY", "protocol": "draft-ietf-ntp-roughtime-08",
		"request_b64": b64(a.Request), "response_b64": b64(a.Response), "public_key_b64": b64(a.PublicKey), "nonce_b64": b64(msg[tag("NONC")]),
		"source_blind_b64": b64(sourceA), "effective_blind_b64": b64(effectiveA), "commitment_b64": b64(commitmentA[:]), "previous_reply_b64": "",
		"expected":                   map[string]any{"midpoint_unix_s": int64(1700000000), "radius_s": int64(1)},
		"causal_exchanges":           map[string]any{"A": exchange("A", a, sourceA, effectiveA, commitmentA[:], nil, 1), "B": exchange("B", b, sourceB, effectiveB, commitmentB[:], a.Response, 200)},
		"causal_expected_utc_ns":     []int64{1699999998000000000, 1700000004000000000},
		"causal_slab_canonical_json": slab,
	}
}

func TestSoftwareOnlyFixtureOriginals(t *testing.T) {
	generated := fixtureOriginals(t)
	data, err := json.MarshalIndent(generated, "", "  ")
	if err != nil {
		t.Fatal(err)
	}
	data = append(data, '\n')
	const path = "testdata/software-only-exchange.json"
	if os.Getenv("NATIVE_CLOCK_V2_SAVE_SOFTWARE_FIXTURE") == "1" {
		if err := os.MkdirAll("testdata", 0755); err != nil {
			t.Fatal(err)
		}
		if err := os.WriteFile(path, data, 0644); err != nil {
			t.Fatal(err)
		}
	}
	saved, err := os.ReadFile(path)
	if err != nil {
		t.Fatal(err)
	}
	var parsed map[string]any
	if err := json.Unmarshal(saved, &parsed); err != nil {
		t.Fatal(err)
	}
	var generatedParsed map[string]any
	if err := json.Unmarshal(data, &generatedParsed); err != nil {
		t.Fatal(err)
	}
	if !reflect.DeepEqual(parsed, generatedParsed) {
		t.Fatal("saved SOFTWARE_ONLY originals differ from deterministic local test generation")
	}
	originals := parsed["causal_exchanges"].(map[string]any)
	for _, id := range []string{"A", "B"} {
		x := originals[id].(map[string]any)
		out, err := call(t, map[string]any{"op": "verify", "request_b64": x["request_b64"], "response_b64": x["response_b64"], "public_key_b64": x["public_key_b64"]})
		if err != nil {
			t.Fatalf("fixture %s failed signature replay: %v", id, err)
		}
		expectedMidpoint := float64(1700000000)
		if id == "B" {
			expectedMidpoint += 2
		}
		if len(out) != 3 || out["midpoint_unix_s"] != expectedMidpoint || out["radius_s"] != float64(1) {
			t.Fatalf("fixture %s wrong diagnostic: %v", id, out)
		}
	}
}
