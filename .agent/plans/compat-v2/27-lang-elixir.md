# 27 — Elixir Language Module

> **Document**: 27 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Overview

**Versions covered**: Elixir 1.11 through 1.17+
**OTP versions**: OTP 24 through 27
**Feature entries target**: 40+
**Parser**: tree-sitter-elixir
**Import resolver**: Follow `alias`/`import`/`use`/`require`, resolve via module naming conventions
**Package registry**: Hex
**Formatter**: `mix format` (canonical)

---

## 2. Elixir Version Model

Elixir has TWO version axes:
1. **Elixir version** (1.11–1.17): Language features
2. **OTP version** (24–27): Runtime/VM features (Erlang/OTP)

Each Elixir version requires a minimum OTP version. The engine must check both.

---

## 3. Feature Database Highlights

```yaml
# Elixir 1.12 — Stepped ranges
- id: elixir.1_12.stepped_ranges
  feature_name: "stepped ranges (first..last//step)"
  introduced: "1.12"
  detection:
    primary:
      ast_type: binary_operator
      match:
        operator: "//"
        context: range
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_stepped_range
    manual_instructions: "Use Enum.take_every/2 on a regular range"
  test:
    before: |
      for i <- 1..100//5, do: IO.puts(i)
    after: |
      for i <- Enum.take_every(1..100, 5), do: IO.puts(i)

# Elixir 1.12 — then/1
- id: elixir.1_12.then
  feature_name: "then/1 (Kernel.then)"
  introduced: "1.12"
  detection:
    primary:
      ast_type: call
      match:
        function: then
        arity: 1
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_pipe_then
        replace:
          style: case_expression_or_anonymous_fn
  test:
    before: |
      value |> then(&process/1)
    after: |
      value |> (fn x -> process(x) end).()

# Elixir 1.14 — dbg/1
- id: elixir.1_14.dbg
  feature_name: "dbg/1 debugging macro"
  introduced: "1.14"
  detection:
    primary:
      ast_type: call
      match:
        function: dbg
  fix:
    strategy: rewrite_expression
    transforms:
      - type: replace_function_call
        replace:
          expression: "IO.inspect({arg}, label: \"{arg}\")"
  test:
    before: |
      result = compute() |> dbg()
    after: |
      result = compute() |> IO.inspect(label: "compute()")

# Elixir 1.14 — PartitionSupervisor
- id: elixir.1_14.partition_supervisor
  feature_name: "PartitionSupervisor"
  introduced: "1.14"
  detection:
    primary:
      ast_type: alias
      match:
        module: PartitionSupervisor
  fix:
    strategy: manual
    manual_instructions: "Use multiple workers under a regular Supervisor"

# Elixir 1.15 — Duration module
- id: elixir.1_15.duration
  feature_name: "Duration module"
  introduced: "1.15"
  detection:
    primary:
      ast_type: call
      match:
        module: Duration
    alternatives:
      - ast_type: alias
        match:
          module: Duration
  fix:
    strategy: manual
    manual_instructions: "Use integer representations (milliseconds/microseconds) directly"

# Elixir 1.15 — Calendar.shift/2
- id: elixir.1_15.calendar_shift
  feature_name: "Date/DateTime/NaiveDateTime.shift/2"
  introduced: "1.15"
  detection:
    primary:
      ast_type: call
      match:
        function: shift
        module_in: [Date, DateTime, NaiveDateTime]
  fix:
    strategy: manual
    manual_instructions: "Use timex library or manual arithmetic with add/2"

# Elixir 1.16 — Multi-letter sigils
- id: elixir.1_16.multi_letter_sigils
  feature_name: "multi-letter sigils (~JSON, ~YAML)"
  introduced: "1.16"
  detection:
    primary:
      ast_type: sigil
      match:
        name_length_gt: 1
  fix:
    strategy: manual
    manual_instructions: "Use function calls instead of sigils"

# Elixir 1.17 — Duration-based functions
- id: elixir.1_17.duration_based_apis
  feature_name: "Duration-based API functions"
  introduced: "1.17"
  detection:
    primary:
      ast_type: call
      match:
        function: sleep
        args_contains_duration: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: convert_duration_to_ms
```

---

## 4. Elixir-Specific Edge Cases

### 4.1 Macros
Elixir heavily uses macros. Macro-generated code may use features from the macro's Elixir version, not the caller's. The engine should:
- Scan source files (before macro expansion)
- NOT scan compiled .beam files
- Flag macro definitions that generate version-specific code as manual review

### 4.2 OTP version dependencies
Some features depend on OTP, not Elixir:
- `ssl` module changes between OTP versions
- `:atomics` module (OTP 21+)
- `:counters` module (OTP 21+)
- `:persistent_term` (OTP 21+)

The engine should check OTP version alongside Elixir version.

### 4.3 Mix project configuration
```elixir
# mix.exs
def project do
  [
    app: :my_app,
    elixir: "~> 1.14",    # Version floor
    deps: deps()
  ]
end
```

The `elixir` field in `mix.exs` declares the version floor.

### 4.4 Protocol implementations
Elixir protocols are like interfaces. Protocol implementations may use version-specific features. The engine should scan protocol implementations alongside regular modules.

### 4.5 Umbrella projects
Elixir umbrella projects contain multiple apps under `apps/`. Each app may have its own version requirement. The engine should treat each app as a separate module.

---

## 5. Integration Points

Standard LanguageBackend. Elixir-specific:
- `mix.exs` parsing for version floor and deps
- `mix compile` for verification
- Hex API for package compatibility
- `mix format` for post-transform formatting
- OTP version tracking alongside Elixir version
- Umbrella project support (multiple apps)
- Macro awareness (don't scan expanded code)
