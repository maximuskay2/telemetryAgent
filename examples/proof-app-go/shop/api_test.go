package shop

// Proof-shop API suite: exercises the HTTP layer against a test server.

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func post(t *testing.T, url, body string) (int, map[string]any) {
	t.Helper()
	resp, err := http.Post(url, "application/json", bytes.NewBufferString(body))
	if err != nil {
		t.Fatalf("post failed: %v", err)
	}
	defer resp.Body.Close()
	var decoded map[string]any
	if err := json.NewDecoder(resp.Body).Decode(&decoded); err != nil {
		t.Fatalf("decode failed: %v", err)
	}
	return resp.StatusCode, decoded
}

func TestHealth(t *testing.T) {
	server := httptest.NewServer(Handler())
	defer server.Close()
	resp, err := http.Get(server.URL + "/health")
	if err != nil {
		t.Fatalf("get failed: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 200 {
		t.Fatalf("got %d; want 200", resp.StatusCode)
	}
}

func TestCheckoutOk(t *testing.T) {
	server := httptest.NewServer(Handler())
	defer server.Close()
	status, decoded := post(t, server.URL+"/checkout",
		`{"items": [{"name": "a", "price": 2.0, "qty": 2}]}`)
	if status != 200 || decoded["total"] != 4.0 {
		t.Fatalf("got %d %v; want 200 total 4", status, decoded)
	}
}

func TestCheckoutValidatesPrice(t *testing.T) {
	server := httptest.NewServer(Handler())
	defer server.Close()
	status, _ := post(t, server.URL+"/checkout",
		`{"items": [{"name": "a", "price": -1, "qty": 1}]}`)
	if status != 422 {
		t.Fatalf("got %d; want 422", status)
	}
}

func TestCheckoutValidatesName(t *testing.T) {
	server := httptest.NewServer(Handler())
	defer server.Close()
	status, _ := post(t, server.URL+"/checkout",
		`{"items": [{"name": "", "price": 1, "qty": 1}]}`)
	if status != 422 {
		t.Fatalf("got %d; want 422", status)
	}
}

func TestCheckoutBulkOrder(t *testing.T) {
	server := httptest.NewServer(Handler())
	defer server.Close()
	status, decoded := post(t, server.URL+"/checkout",
		`{"items": [{"name": "n0", "price": 10.0, "qty": 10},`+
			` {"name": "n1", "price": 10.0, "qty": 10},`+
			` {"name": "n2", "price": 10.0, "qty": 10}]}`)
	if status != 200 || decoded["discount"] != 15.0 {
		t.Fatalf("got %d %v; want 200 discount 15", status, decoded)
	}
}

func TestCheckoutSingleBulkLineHasNoDiscount(t *testing.T) {
	server := httptest.NewServer(Handler())
	defer server.Close()
	status, decoded := post(t, server.URL+"/checkout",
		`{"items": [{"name": "a", "price": 1.0, "qty": 25}]}`)
	if status != 200 || decoded["discount"] != 0.0 {
		t.Fatalf("got %d %v; want 200 discount 0", status, decoded)
	}
}

func TestCheckoutZeroQtyLine(t *testing.T) {
	server := httptest.NewServer(Handler())
	defer server.Close()
	status, decoded := post(t, server.URL+"/checkout",
		`{"items": [{"name": "a", "price": 3.0, "qty": 0}]}`)
	if status != 200 || decoded["total"] != 0.0 {
		t.Fatalf("got %d %v; want 200 total 0", status, decoded)
	}
}

func TestUnknownRouteIs404(t *testing.T) {
	server := httptest.NewServer(Handler())
	defer server.Close()
	resp, err := http.Get(server.URL + "/nope")
	if err != nil {
		t.Fatalf("get failed: %v", err)
	}
	defer resp.Body.Close()
	if resp.StatusCode != 404 {
		t.Fatalf("got %d; want 404", resp.StatusCode)
	}
}
