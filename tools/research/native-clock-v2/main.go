// native-clock-v2 is a bounded offline Roughtime wire diagnostic.
// It does not open sockets, select trusted sources or grant native authority.
package main

import (
	"bytes"
	"crypto/ed25519"
	"encoding/base64"
	"encoding/binary"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"

	"github.com/cloudflare/roughtime/protocol"
)

type inputMessage struct {
	Op            string `json:"op"`
	PreviousReply string `json:"previous_reply_b64"`
	Blind         string `json:"blind_b64"`
	PublicKey     string `json:"public_key_b64"`
	Request       string `json:"request_b64"`
	Response      string `json:"response_b64"`
}

func decodeB64(value string, name string) ([]byte, error) {
	decoded, err := base64.StdEncoding.Strict().DecodeString(value)
	if err != nil {
		return nil, fmt.Errorf("%s: invalid base64: %w", name, err)
	}
	return decoded, nil
}

// strictFrame preserves the draft08 framing assertion discarded by the
// upstream verifier. Decode also rejects duplicate/out-of-order protocol tags.
func strictFrame(packet []byte) (map[uint32][]byte, error) {
	if len(packet) < 12 || !bytes.Equal(packet[:8], []byte("ROUGHTIM")) {
		return nil, errors.New("draft08 requires ROUGHTIM framing")
	}
	if uint64(binary.LittleEndian.Uint32(packet[8:12])) != uint64(len(packet)-12) {
		return nil, errors.New("frame length differs from exact original packet")
	}
	fields, err := protocol.Decode(packet[12:])
	if err != nil {
		return nil, err
	}
	version := fields[binary.LittleEndian.Uint32([]byte("VER\x00"))]
	if len(version) != 4 || binary.LittleEndian.Uint32(version) != uint32(protocol.VersionDraft08) {
		return nil, errors.New("sole version must be draft08")
	}
	return fields, nil
}

func strictOriginals(request, response []byte) ([]byte, error) {
	requestFields, err := strictFrame(request)
	if err != nil {
		return nil, err
	}
	responseFields, err := strictFrame(response)
	if err != nil {
		return nil, err
	}
	nonce := requestFields[binary.LittleEndian.Uint32([]byte("NONC"))]
	if len(nonce) != 32 {
		return nil, errors.New("draft08 request nonce must be 32 bytes")
	}
	responseNonce := responseFields[binary.LittleEndian.Uint32([]byte("NONC"))]
	if !bytes.Equal(nonce, responseNonce) {
		return nil, errors.New("response nonce differs from original request")
	}
	indexBytes := responseFields[binary.LittleEndian.Uint32([]byte("INDX"))]
	if len(indexBytes) != 4 {
		return nil, errors.New("INDX must be uint32")
	}
	path, ok := responseFields[binary.LittleEndian.Uint32([]byte("PATH"))]
	if !ok || len(path)%32 != 0 {
		return nil, errors.New("PATH must contain draft08 hashes")
	}
	index := binary.LittleEndian.Uint32(indexBytes)
	if index>>uint(len(path)/32) != 0 {
		return nil, errors.New("INDX contains unused path bits")
	}
	// Keep the upstream request minimum-size and nonce validation as well.
	if _, err := protocol.ParseRequest(request); err != nil {
		return nil, err
	}
	return nonce, nil
}

func run(input io.Reader, output io.Writer) error {
	var in inputMessage
	decoder := json.NewDecoder(io.LimitReader(input, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&in); err != nil {
		return fmt.Errorf("input JSON: %w", err)
	}
	var extra any
	if err := decoder.Decode(&extra); err != io.EOF {
		return errors.New("input must be one JSON object")
	}
	publicKey, err := decodeB64(in.PublicKey, "public_key_b64")
	if err != nil {
		return err
	}
	if len(publicKey) != ed25519.PublicKeySize {
		return errors.New("public key must be 32 bytes")
	}
	switch in.Op {
	case "request":
		blind, err := decodeB64(in.Blind, "blind_b64")
		if err != nil {
			return err
		}
		if len(blind) != 32 {
			return errors.New("draft08 blind must be 32 bytes")
		}
		previous, err := decodeB64(in.PreviousReply, "previous_reply_b64")
		if err != nil {
			return err
		}
		nonce, _, request, err := protocol.CreateRequest([]protocol.Version{protocol.VersionDraft08}, bytes.NewReader(blind), previous, publicKey)
		if err != nil {
			return err
		}
		return json.NewEncoder(output).Encode(map[string]string{"nonce_b64": base64.StdEncoding.EncodeToString(nonce), "request_b64": base64.StdEncoding.EncodeToString(request)})
	case "verify":
		request, err := decodeB64(in.Request, "request_b64")
		if err != nil {
			return err
		}
		response, err := decodeB64(in.Response, "response_b64")
		if err != nil {
			return err
		}
		nonce, err := strictOriginals(request, response)
		if err != nil {
			return err
		}
		midpoint, radius, err := protocol.VerifyReply([]protocol.Version{protocol.VersionDraft08}, response, publicKey, nonce)
		if err != nil {
			return err
		}
		return json.NewEncoder(output).Encode(map[string]any{"protocol": "draft-ietf-ntp-roughtime-08", "midpoint_unix_s": midpoint.Unix(), "radius_s": int64(radius.Seconds())})
	default:
		return errors.New("op must be request or verify")
	}
}

func main() {
	if err := run(os.Stdin, os.Stdout); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}
