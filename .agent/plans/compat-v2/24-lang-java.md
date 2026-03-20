# 24 — Java Language Module

> **Document**: 24 of 37
> **Milestone**: M9 — Language modules & edge cases
> **Status**: Draft

---

## 1. Overview

**Versions covered**: Java 11 (LTS) through 21 (LTS)
**Feature entries target**: 100+
**Parser**: tree-sitter-java
**Import resolver**: Follow `import` declarations, resolve via package/directory structure
**Package registry**: Maven Central
**Formatter**: google-java-format (optional)

---

## 2. Java Version Model

Java uses LTS (Long-Term Support) versions: 11, 17, 21. Features between LTS versions may be "preview" before becoming stable. The engine tracks both:
- **Stable since**: When the feature became a standard part of the language
- **Preview since**: When the feature was first available as --enable-preview

---

## 3. Feature Database Highlights

```yaml
# Java 14 — Records
- id: java.14.records
  feature_name: "record classes"
  introduced: "16"  # Preview in 14, stable in 16
  preview_since: "14"
  detection:
    primary:
      ast_type: record_declaration
  fix:
    strategy: manual
    manual_instructions: |
      Replace record with a standard class:
        record Point(int x, int y) {}
        →
        public final class Point {
            private final int x, y;
            public Point(int x, int y) { this.x = x; this.y = y; }
            public int x() { return x; }
            public int y() { return y; }
            // equals, hashCode, toString
        }
      Consider using Lombok @Value as an intermediate.

# Java 14 — Switch expressions
- id: java.14.switch_expression
  feature_name: "switch expression"
  introduced: "14"
  detection:
    primary:
      ast_type: switch_expression
  fix:
    strategy: manual
    manual_instructions: "Rewrite as switch statement with variable assignment"

# Java 15 — Text blocks
- id: java.15.text_blocks
  feature_name: 'text blocks ("""triple quotes""")'
  introduced: "15"
  detection:
    primary:
      ast_type: text_block
  fix:
    strategy: rewrite_expression
    transforms:
      - type: rewrite_text_block
        replace:
          style: string_concatenation
  test:
    before: |
      String query = """
          SELECT *
          FROM users
          WHERE active = true
          """;
    after: |
      String query = "SELECT *\n"
          + "FROM users\n"
          + "WHERE active = true\n";

# Java 16 — Pattern matching instanceof
- id: java.16.pattern_instanceof
  feature_name: "pattern matching for instanceof"
  introduced: "16"
  detection:
    primary:
      ast_type: instanceof_expression
      match:
        has_pattern: true
  fix:
    strategy: rewrite_expression
    transforms:
      - type: split_instanceof_cast
  test:
    before: |
      if (obj instanceof String s) {
          System.out.println(s.length());
      }
    after: |
      if (obj instanceof String) {
          String s = (String) obj;
          System.out.println(s.length());
      }

# Java 17 — Sealed classes
- id: java.17.sealed_classes
  feature_name: "sealed classes"
  introduced: "17"
  detection:
    primary:
      ast_type: class_declaration
      match:
        modifiers_contains: sealed
  fix:
    strategy: manual
    manual_instructions: "Remove 'sealed' and 'permits'. Use abstract class with documented constraints."

# Java 21 — Virtual threads
- id: java.21.virtual_threads
  feature_name: "virtual threads"
  introduced: "21"
  detection:
    primary:
      ast_type: method_invocation
      match:
        object: Thread
        method: ofVirtual
    alternatives:
      - ast_type: method_invocation
        match:
          receiver: Executors
          method: newVirtualThreadPerTaskExecutor
  fix:
    strategy: manual
    manual_instructions: "Use platform threads or a thread pool (Executors.newCachedThreadPool)"

# Java 21 — Pattern matching in switch
- id: java.21.switch_pattern_matching
  feature_name: "pattern matching in switch"
  introduced: "21"
  detection:
    primary:
      ast_type: switch_expression
      match:
        has_pattern_label: true
  fix:
    strategy: manual
    manual_instructions: "Rewrite as if/else if chain with instanceof checks"
```

---

## 4. Java-Specific Edge Cases

### 4.1 Preview features
Features marked `--enable-preview` are not stable. Code using previews only works with the exact compiler version. The engine should flag preview features differently from stable features.

### 4.2 Multi-module projects (Maven/Gradle)
Java projects may have multiple modules with separate `pom.xml` or `build.gradle`. Each module may target a different Java version.

### 4.3 Annotation processors
Lombok, MapStruct, etc. generate code at compile time. Generated code should not be scanned. Detect `target/generated-sources` and skip.

### 4.4 Java module system (JPMS)
`module-info.java` (Java 9+) declares module boundaries. If present, import resolution must respect module exports/requires.

---

## 5. Integration Points

Standard LanguageBackend. Java-specific:
- `javac` for compilation verification
- Maven/Gradle for dependency analysis
- Maven Central API for package registry
- `pom.xml` / `build.gradle` parsing for version floor
- google-java-format for optional formatting
