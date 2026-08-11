package compiler

import (
	"github.com/google/cel-go/cel"
)

type Validation struct {
	Message           string
	MessageExpression cel.Program
	Program           cel.Program
	// AST is the retained abstract syntax tree for Program, set only when CompileValidation
	// was called with trace=true. It is required by trace.Build to map a traced node id back
	// to its source text; nil otherwise.
	AST *cel.Ast
}
