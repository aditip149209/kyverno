package trace

import (
	"fmt"
	"sort"

	"github.com/google/cel-go/cel"
	celast "github.com/google/cel-go/common/ast"
	"github.com/google/cel-go/common/types/ref"
)

// NodeTrace is the resolved value of a single sub-expression within a larger CEL expression.
type NodeTrace struct {
	// Expression is the rendered source text of just this sub-expression, e.g. "object.metadata.labels".
	Expression string
	// Value is the sub-expression's resolved value, stringified. Empty if the node never evaluated
	// (e.g. short-circuited by &&/||) or errored.
	Value string
	// Error is set when this specific node produced an evaluation error (distinct from the value it produced).
	Error string
}

// ExpressionTrace is the full per-node breakdown of one compiled expression's evaluation.
type ExpressionTrace struct {
	// Source is the complete expression string as written in the policy.
	Source string
	// Nodes are the sub-expressions that were evaluated, in left-to-right source order.
	Nodes []NodeTrace
	// Result is the top-level outcome, stringified.
	Result string
}

// Build turns the raw output of a tracked CEL evaluation into a curated, source-ordered
// ExpressionTrace. It requires the AST to have been retained at compile time (see
// compiler.CompileValidation's trace parameter) and the Program to have been built with
// cel.EvalOptions(cel.OptTrackState), otherwise details will be nil and Build returns just
// the top-level result with no per-node breakdown.
func Build(source string, ast *cel.Ast, result ref.Val, details *cel.EvalDetails) ExpressionTrace {
	et := ExpressionTrace{
		Source: source,
		Result: stringify(result),
	}
	if details == nil || ast == nil {
		return et
	}
	state := details.State()
	native := ast.NativeRep()
	sourceInfo := native.SourceInfo()

	idToExpr := map[int64]celast.Expr{}
	celast.PreOrderVisit(native.Expr(), celast.NewExprVisitor(func(e celast.Expr) {
		idToExpr[e.ID()] = e
	}))

	type located struct {
		start int32
		node  NodeTrace
	}
	var entries []located
	for _, id := range state.IDs() {
		node, ok := idToExpr[id]
		if !ok {
			continue
		}
		text, err := cel.ExprToString(node, sourceInfo)
		if err != nil || text == "" {
			continue
		}
		val, ok := state.Value(id)
		nt := NodeTrace{Expression: text}
		if ok {
			nt.Value = stringify(val)
		}
		offset, _ := sourceInfo.GetOffsetRange(id)
		entries = append(entries, located{start: offset.Start, node: nt})
	}
	sort.SliceStable(entries, func(i, j int) bool { return entries[i].start < entries[j].start })
	for _, e := range entries {
		et.Nodes = append(et.Nodes, e.node)
	}
	return et
}

func stringify(v ref.Val) string {
	if v == nil {
		return ""
	}
	return fmt.Sprintf("%v", v.Value())
}
