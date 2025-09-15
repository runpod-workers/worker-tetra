#!/bin/bash

echo "Testing handler with all test_*.json files..."

failed_tests=""
test_count=0
passed_count=0

for test_file in test_*.json; do
    if [ ! -f "$test_file" ]; then
        echo "No test_*.json files found"
        exit 1
    fi
    
    test_count=$((test_count + 1))
    echo "Testing with $test_file..."
    
    # Run the test and capture output
    output=$(uv run python handler.py --test_input "$(cat "$test_file")" 2>&1)
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        echo "✓ $test_file: PASSED"
        passed_count=$((passed_count + 1))
    else
        echo "✗ $test_file: FAILED (exit code: $exit_code)"
        echo "Error output:"
        echo "$output" | head -10
        echo "---"
        failed_tests="$failed_tests $test_file"
    fi
done

echo ""
echo "Test Results: $passed_count/$test_count tests passed"

if [ -z "$failed_tests" ]; then
    echo "All tests passed!"
    exit 0
else
    echo "Failed tests:$failed_tests"
    exit 1
fi
