package shop

import (
	"encoding/json"
	"errors"
	"io"
	"log"
	"math"
	"net/http"
	"runtime/debug"
)

// itemIn is the raw wire item. Pointer fields make missing keys a 422,
// matching the Python proof app's validation.
type itemIn struct {
	Name     *string  `json:"name"`
	Price    *float64 `json:"price"`
	Qty      *int     `json:"qty"`
	Currency *string  `json:"currency"`
}

type checkoutIn struct {
	Items []itemIn `json:"items"`
}

func parseItems(body io.Reader) ([]Item, error) {
	decoder := json.NewDecoder(body)
	var payload checkoutIn
	if err := decoder.Decode(&payload); err != nil {
		return nil, err
	}
	var extra struct{}
	if err := decoder.Decode(&extra); err != io.EOF {
		return nil, errors.New("trailing data")
	}
	items := make([]Item, 0, len(payload.Items))
	for _, raw := range payload.Items {
		if raw.Name == nil || *raw.Name == "" {
			return nil, errors.New("bad name")
		}
		if raw.Price == nil || *raw.Price < 0 {
			return nil, errors.New("bad price")
		}
		if raw.Qty == nil || *raw.Qty < 0 {
			return nil, errors.New("bad qty")
		}
		currency := "USD"
		if raw.Currency != nil {
			currency = *raw.Currency
		}
		items = append(items, Item{
			Name:       *raw.Name,
			PriceCents: int64(math.Round(*raw.Price * 100)),
			Qty:        *raw.Qty,
			Currency:   currency,
		})
	}
	return items, nil
}

func writeJSON(writer http.ResponseWriter, status int, value any) {
	writer.Header().Set("content-type", "application/json")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(value)
}

// withRecovery logs the real goroutine stack on panic and answers 500.
// The trace format is identical to an unrecovered net/http panic.
func withRecovery(next http.Handler) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		defer func() {
			if recovered := recover(); recovered != nil {
				log.Printf("panic: %v\n%s", recovered, debug.Stack()) // the production trace
				writeJSON(writer, http.StatusInternalServerError, map[string]string{
					"detail": "internal error",
				})
			}
		}()
		next.ServeHTTP(writer, request)
	})
}

// NewMux routes the proof shop API.
func NewMux() *http.ServeMux {
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodGet {
			writeJSON(writer, http.StatusNotFound, map[string]string{"detail": "not found"})
			return
		}
		writeJSON(writer, http.StatusOK, map[string]string{"status": "ok"})
	})
	mux.HandleFunc("/checkout", func(writer http.ResponseWriter, request *http.Request) {
		if request.Method != http.MethodPost {
			writeJSON(writer, http.StatusNotFound, map[string]string{"detail": "not found"})
			return
		}
		items, err := parseItems(request.Body)
		if err != nil {
			writeJSON(writer, 422, map[string]string{"detail": "invalid items"})
			return
		}
		// No recover here on purpose: the empty-cart panic must crash
		// with a full goroutine stack so the forwarder ships it to
		// TelemetryAgent.
		writeJSON(writer, http.StatusOK, Summarize(items))
	})
	return mux
}

// Handler is the full stack: routes plus the panic-to-500 barrier.
func Handler() http.Handler {
	return withRecovery(NewMux())
}
