<?php

declare(strict_types=1);

// Built-in-server router (php -S ... -t public public/index.php): thin
// wrapper over ProofShop\Shop::handle. Uncaught errors (e.g. the
// empty-cart DivisionByZeroError) print as fatals on stderr.

require __DIR__.'/../vendor/autoload.php';

use ProofShop\Shop;

// The built-in server answers 200 even when the router dies with a fatal,
// so remap fatal shutdowns to 500. This prints nothing: the engine's own
// fatal + stack trace on stderr stays the production trace, byte for byte.
register_shutdown_function(function () {
    $err = error_get_last();
    if ($err !== null && ($err['type'] & (E_ERROR | E_CORE_ERROR | E_COMPILE_ERROR | E_USER_ERROR | E_RECOVERABLE_ERROR | E_PARSE))) {
        if (!headers_sent()) {
            http_response_code(500);
        }
    }
});

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';
$body = file_get_contents('php://input') ?: '';

[$code, $data] = Shop::handle($method, $path, $body);
http_response_code($code);
header('content-type: application/json');
echo json_encode($data);
