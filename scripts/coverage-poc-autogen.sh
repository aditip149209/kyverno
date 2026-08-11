#!/usr/bin/env bash
# Proof-of-method for validating "does test/conformance/chainsaw/autogen/**
# actually exercise pkg/autogen/**" with real Go coverage instrumentation
# instead of trusting the folder names to line up.
#
# SCOPE: this is the fast, cluster-free slice of that proof. It builds the
# kyverno CLI with -cover and runs it -- through its real `apply` entrypoint,
# not a direct package import -- against one of the actual policy fixtures
# from test/conformance/chainsaw/autogen/should-autogen/, then inspects
# which packages the run actually touched via `go tool covdata`.
#
# It does NOT stand in for the full validation: the real chainsaw suite
# drives a live admission webhook via a kind cluster, which is a materially
# different (and narrower, test-by-test) code path than the CLI's apply
# command. Building that out is the natural next step; this script only
# proves the instrumentation/inspection method works and that pkg/autogen
# is genuinely reachable from a realistic autogen-eligible policy, not that
# every chainsaw/autogen test case maps 1:1 to pkg/autogen alone.
#
# Usage: scripts/coverage-poc-autogen.sh

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "==> Building coverage-instrumented kyverno CLI..."
go build -cover -o "$WORKDIR/kyverno-instrumented" ./cmd/cli/kubectl-kyverno

echo "==> Deriving a standalone policy from a real chainsaw autogen fixture..."
FIXTURE=test/conformance/chainsaw/autogen/should-autogen/policy.yaml
sed 's/(\$test\.metadata\.name)/coverage-poc-autogen/' "$FIXTURE" > "$WORKDIR/policy.yaml"

cat > "$WORKDIR/resource.yaml" <<'EOF'
apiVersion: v1
kind: Pod
metadata:
  name: coverage-poc-pod
spec:
  containers:
  - name: test
    image: nginx:1.25.3
EOF

COVDIR="$WORKDIR/covdata"
mkdir -p "$COVDIR"

echo "==> Running 'kyverno apply' (exercises pkg/autogen via ComputeRules)..."
GOCOVERDIR="$COVDIR" "$WORKDIR/kyverno-instrumented" apply "$WORKDIR/policy.yaml" \
  --resource "$WORKDIR/resource.yaml"

echo
echo "==> Coverage for pkg/autogen/** from this single CLI invocation:"
go tool covdata percent -i="$COVDIR" 2>&1 | grep -E "pkg/autogen" || {
  echo "FAIL: pkg/autogen was not touched at all -- method or fixture is broken."
  exit 1
}

TOTAL=$(go tool covdata percent -i="$COVDIR" 2>&1 | wc -l)
TOUCHED=$(go tool covdata percent -i="$COVDIR" 2>&1 | grep -vc "coverage: 0.0%")
echo
echo "==> For context: $TOUCHED / $TOTAL instrumented packages saw any coverage"
echo "    at all from this run (the CLI apply path is much broader than"
echo "    autogen alone -- this number is expected to be large, and is not"
echo "    itself the claim being proven)."
