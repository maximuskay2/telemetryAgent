// Command proofshop runs the proof shop API: the app TelemetryAgent
// watches end to end.
package main

import (
	"fmt"
	"log"
	"net/http"
	"os"

	"proofshop/shop"
)

func main() {
	port := "8324"
	if len(os.Args) > 1 {
		port = os.Args[1]
	}
	host := os.Getenv("HOST")
	if host == "" {
		host = "127.0.0.1"
	}
	addr := host + ":" + port
	fmt.Println("proof-shop-go listening on " + addr)
	log.Fatal(http.ListenAndServe(addr, shop.Handler()))
}
