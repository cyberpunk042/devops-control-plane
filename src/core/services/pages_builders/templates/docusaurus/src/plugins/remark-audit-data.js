/**
 * remark-audit-data — Custom remark plugin for :::audit-data directives.
 *
 * Reads pre-computed audit data from _audit_data.json (written by the
 * Python enrichment pipeline) and replaces :::audit-data container
 * directive nodes with pre-rendered HTML <details> blocks.
 *
 * This plugin is meant to be added to `remarkPlugins` (not
 * `beforeDefaultRemarkPlugins`) so that `remark-directive` has already
 * parsed the ::: syntax into `containerDirective` AST nodes.
 *
 * Zero external dependencies — uses only Node.js builtins.
 */

'use strict';

const fs = require('fs');
const path = require('path');

module.exports = function remarkAuditData() {
    // ── Load pre-computed data once when the plugin is initialized ──
    const dataPath = path.resolve(process.cwd(), '_audit_data.json');
    let auditMap = {};
    try {
        auditMap = JSON.parse(fs.readFileSync(dataPath, 'utf-8'));
    } catch {
        // No audit data available — plugin will be a no-op for all files.
    }

    const hasData = Object.keys(auditMap).length > 0;

    // ── Transformer (called per file) ──────────────────────────────
    return (tree, file) => {
        if (!hasData) return;

        // Determine relative path from docs/ directory
        const docsDir = path.resolve(process.cwd(), 'docs');
        const filePath = file.path || (file.history && file.history[0]) || '';
        if (!filePath) return;

        // Compute the lookup key: relative to docs/, with .md extension
        // (the Python side stores keys with .md, not .mdx)
        let relPath = path.relative(docsDir, filePath);
        relPath = relPath.replace(/\.mdx$/, '.md');

        const entry = auditMap[relPath];
        if (!entry || !entry.html) return;

        // Walk the AST and replace containerDirective nodes named 'audit-data'
        walk(tree, entry.html);
    };
};


/**
 * Recursively walk the MDAST and replace :::audit-data nodes with HTML.
 *
 * @param {object} node - Current AST node.
 * @param {string} html - Pre-rendered HTML to insert.
 */
function walk(node, html) {
    if (!node.children) return;

    for (let i = 0; i < node.children.length; i++) {
        const child = node.children[i];

        if (child.type === 'containerDirective' && child.name === 'audit-data') {
            // Replace the directive node with a raw HTML node
            node.children[i] = {
                type: 'html',
                value: html,
            };
            // Don't recurse into the replaced node — skip to next sibling
        } else {
            walk(child, html);
        }
    }
}
