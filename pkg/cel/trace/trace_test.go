package trace

import (
	"context"
	"testing"

	"github.com/google/cel-go/cel"
	"github.com/kyverno/kyverno/pkg/cel/compiler"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
	admissionregistrationv1 "k8s.io/api/admissionregistration/v1"
)

// TestBuild_RequireAppLabel demonstrates the trace mechanism end to end against the same
// expression used in vpol-test.yaml: "has(object.metadata.labels) && 'app' in
// object.metadata.labels". Run with `go test ./pkg/cel/trace/... -run TestBuild -v` to see the
// per-expression breakdown for a Pod that fails the check and one that passes it.
func TestBuild_RequireAppLabel(t *testing.T) {
	env, err := compiler.NewBaseEnv()
	require.NoError(t, err)
	env, err = env.Extend(cel.Variable("object", cel.DynType))
	require.NoError(t, err)

	rule := admissionregistrationv1.Validation{
		Expression: "has(object.metadata.labels) && 'app' in object.metadata.labels",
	}
	validation, errs := compiler.CompileValidation(nil, env, rule, true)
	require.Empty(t, errs)
	require.NotNil(t, validation.AST)

	tests := []struct {
		name       string
		object     map[string]any
		wantResult string
	}{
		{
			name: "missing app label",
			object: map[string]any{
				"metadata": map[string]any{
					"labels": map[string]any{"team": "platform"},
				},
			},
			wantResult: "false",
		},
		{
			name: "has app label",
			object: map[string]any{
				"metadata": map[string]any{
					"labels": map[string]any{"app": "nginx"},
				},
			},
			wantResult: "true",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			out, details, err := validation.Program.ContextEval(context.TODO(), map[string]any{
				"object": tt.object,
			})
			require.NoError(t, err)
			require.NotNil(t, details, "details must be non-nil: Program was compiled with trace=true")

			et := Build(rule.Expression, validation.AST, out, details)
			assert.Equal(t, tt.wantResult, et.Result)
			assert.NotEmpty(t, et.Nodes, "expected at least one traced sub-expression")

			t.Logf("expression: %s", et.Source)
			for _, n := range et.Nodes {
				t.Logf("  %-55s -> %s", n.Expression, n.Value)
			}
			t.Logf("  result: %s", et.Result)
		})
	}
}
