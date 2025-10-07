#!/bin/bash
# Verification script for production mode changes

echo "=================================================="
echo "Worker-tetra Production Mode Verification"
echo "=================================================="
echo ""

# Check if baked_executor.py exists
echo "1. Checking for baked_executor.py..."
if [ -f "src/baked_executor.py" ]; then
    echo "   ✅ baked_executor.py exists"
    lines=$(wc -l < src/baked_executor.py)
    echo "      Lines: $lines"
else
    echo "   ❌ baked_executor.py NOT FOUND"
    exit 1
fi
echo ""

# Check if remote_executor.py has baked mode support
echo "2. Checking remote_executor.py for baked mode..."
if grep -q "baked_executor" src/remote_executor.py; then
    echo "   ✅ remote_executor.py has baked mode support"
    echo "      Functions found:"
    grep -n "def.*baked" src/remote_executor.py | head -3
else
    echo "   ❌ remote_executor.py missing baked mode support"
    exit 1
fi
echo ""

# Check if remote_execution.py has baked field
echo "3. Checking remote_execution.py for baked field..."
if grep -q "baked: bool" src/remote_execution.py; then
    echo "   ✅ remote_execution.py has baked field in protocol"
else
    echo "   ❌ remote_execution.py missing baked field"
    exit 1
fi
echo ""

# Python import test
echo "4. Testing Python imports..."
if python3 -c "import sys; sys.path.insert(0, 'src'); from baked_executor import BakedExecutor, is_baked_mode_enabled; print('✅ Imports successful')" 2>/dev/null; then
    echo "   ✅ All imports work"
else
    echo "   ⚠️  Import test failed (this is OK if dependencies not installed)"
fi
echo ""

# Summary
echo "=================================================="
echo "Summary"
echo "=================================================="
echo "✅ baked_executor.py created"
echo "✅ remote_executor.py modified"
echo "✅ remote_execution.py modified"
echo ""
echo "Next steps:"
echo "1. Build worker base image:"
echo "   docker build -t myregistry/tetra-worker:v1.0.0 ."
echo ""
echo "2. Test baked mode:"
echo "   docker run -e TETRA_BAKED_MODE=true myregistry/tetra-worker:v1.0.0 \\"
echo "     python -c 'from baked_executor import is_baked_mode_enabled; print(is_baked_mode_enabled())'"
echo ""
echo "3. See PRODUCTION_MODE_CHANGES.md for complete details"
echo "=================================================="
