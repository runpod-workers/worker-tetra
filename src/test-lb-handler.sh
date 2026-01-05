#!/bin/bash

set -e

echo "Testing Load Balancer handler with /execute endpoint..."

# Configuration
PORT=80
HOST="localhost"
TEST_TIMEOUT=30
SERVER_PID=""

# Cleanup function
cleanup() {
    if [ -n "$SERVER_PID" ]; then
        echo "Stopping FastAPI server (PID: $SERVER_PID)..."
        kill $SERVER_PID 2>/dev/null || true
        wait $SERVER_PID 2>/dev/null || true
    fi
}

# Set up trap to ensure cleanup on exit
trap cleanup EXIT

# Start FastAPI server in background
echo "Starting FastAPI server on port $PORT..."
PYTHONPATH=. uv run python3 -m uvicorn lb_handler:app --host $HOST --port $PORT --log-level error > /tmp/lb_handler.log 2>&1 &
SERVER_PID=$!

# Wait for server to be ready
echo "Waiting for server to be ready..."
attempt=0
while [ $attempt -lt $TEST_TIMEOUT ]; do
    if curl -s -f "http://$HOST:$PORT/health" > /dev/null 2>&1; then
        echo "✓ Server is ready"
        break
    fi
    attempt=$((attempt + 1))
    sleep 1

    if [ $attempt -eq $TEST_TIMEOUT ]; then
        echo "✗ Server failed to start after ${TEST_TIMEOUT}s"
        echo "Server logs:"
        cat /tmp/lb_handler.log
        exit 1
    fi
done

# Test /health endpoint
echo ""
echo "Testing /health endpoint..."
health_response=$(curl -s "http://$HOST:$PORT/health")
echo "Response: $health_response"

# Run /execute tests
echo ""
echo "Testing /execute endpoint with test files..."

failed_tests=""
test_count=0
passed_count=0

for test_file in tests/test_*.json; do
    if [ ! -f "$test_file" ]; then
        echo "No test_*.json files found"
        exit 1
    fi

    test_count=$((test_count + 1))
    echo ""
    echo "Testing with $test_file..."

    # Send request to /execute endpoint
    response=$(curl -s -X POST "http://$HOST:$PORT/execute" \
        -H "Content-Type: application/json" \
        -d "$(cat "$test_file")")

    # Check if response contains success or error
    if echo "$response" | grep -q '"success":true'; then
        echo "✓ $test_file: PASSED"
        echo "  Result: $(echo "$response" | python3 -m json.tool 2>/dev/null | head -5)"
        passed_count=$((passed_count + 1))
    elif echo "$response" | grep -q '"success":false'; then
        echo "✗ $test_file: FAILED"
        echo "  Error: $(echo "$response" | python3 -c "import sys, json; d=json.load(sys.stdin); print(d.get('error', 'Unknown error'))" 2>/dev/null || echo 'Unknown error')"
        failed_tests="$failed_tests $test_file"
    else
        echo "✗ $test_file: FAILED (Invalid response)"
        echo "  Response: $(echo "$response" | head -c 100)"
        failed_tests="$failed_tests $test_file"
    fi
done

echo ""
echo "============================================"
echo "Test Results: $passed_count/$test_count tests passed"
echo "============================================"

if [ -z "$failed_tests" ]; then
    echo "✓ All tests passed!"
    exit 0
else
    echo "✗ Failed tests:$failed_tests"
    exit 1
fi
