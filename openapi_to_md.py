"""
openapi_to_md.py
Haalt een OpenAPI/Swagger JSON-spec op en converteert die naar Markdown.

Gebruik:
    python openapi_to_md.py https://example.com/openapi.json --title "Mijn API"
    python openapi_to_md.py spec.json --out api_docs.md
"""

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urljoin

import yaml


def load_spec(source: str) -> dict:
    """Laad spec van URL of bestandspad."""
    if source.startswith("http"):
        import urllib.request
        with urllib.request.urlopen(source, timeout=30) as r:
            raw = r.read().decode()
    else:
        raw = Path(source).read_text(encoding="utf-8")

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return yaml.safe_load(raw)


def method_badge(method: str) -> str:
    return f"**`{method.upper()}`**"


def render_schema(schema: dict, indent: int = 0) -> str:
    if not schema:
        return ""
    lines = []
    prefix = "  " * indent

    if "$ref" in schema:
        lines.append(f"{prefix}→ `{schema['$ref'].split('/')[-1]}`")
        return "\n".join(lines)

    typ = schema.get("type", "object")

    if typ == "object" or "properties" in schema:
        for name, prop in schema.get("properties", {}).items():
            required = name in schema.get("required", [])
            req_mark = " *(required)*" if required else ""
            prop_type = prop.get("type") or (prop.get("$ref", "").split("/")[-1]) or "object"
            desc = prop.get("description", "")
            lines.append(f"{prefix}- **{name}**{req_mark} `{prop_type}` {desc}".rstrip())
            if prop.get("properties") or prop.get("$ref"):
                lines.append(render_schema(prop, indent + 1))
    elif typ == "array":
        items = schema.get("items", {})
        item_type = items.get("type") or items.get("$ref", "").split("/")[-1] or "object"
        lines.append(f"{prefix}Array van `{item_type}`")
    else:
        lines.append(f"{prefix}`{typ}`")

    return "\n".join(filter(None, lines))


def resolve_ref(spec: dict, ref: str) -> dict:
    parts = ref.lstrip("#/").split("/")
    obj = spec
    for p in parts:
        obj = obj.get(p, {})
    return obj


def render_params(params: list, spec: dict) -> str:
    if not params:
        return ""
    rows = ["| Naam | In | Type | Verplicht | Omschrijving |",
            "| ---- | -- | ---- | --------- | ------------ |"]
    for p in params:
        if "$ref" in p:
            p = resolve_ref(spec, p["$ref"])
        name     = p.get("name", "")
        location = p.get("in", "")
        required = "Ja" if p.get("required") else "Nee"
        schema   = p.get("schema", {})
        typ      = schema.get("type", "") or schema.get("$ref", "").split("/")[-1]
        desc     = p.get("description", "").replace("\n", " ")
        rows.append(f"| `{name}` | {location} | `{typ}` | {required} | {desc} |")
    return "\n".join(rows)


def render_request_body(body: dict, spec: dict) -> str:
    if not body:
        return ""
    lines = ["**Request body**"]
    for media_type, media in body.get("content", {}).items():
        lines.append(f"\nContent-Type: `{media_type}`")
        schema = media.get("schema", {})
        if "$ref" in schema:
            schema = resolve_ref(spec, schema["$ref"])
        if schema:
            lines.append("\n" + render_schema(schema))
        example = media.get("example") or schema.get("example")
        if example:
            lines.append(f"\n**Voorbeeld:**\n```json\n{json.dumps(example, indent=2, ensure_ascii=False)}\n```")
    return "\n".join(lines)


def render_responses(responses: dict, spec: dict) -> str:
    if not responses:
        return ""
    lines = ["**Responses**", ""]
    for code, resp in responses.items():
        if "$ref" in resp:
            resp = resolve_ref(spec, resp["$ref"])
        desc = resp.get("description", "")
        lines.append(f"- **{code}** — {desc}")
        for media_type, media in resp.get("content", {}).items():
            schema = media.get("schema", {})
            if "$ref" in schema:
                schema = resolve_ref(spec, schema["$ref"])
            if schema:
                lines.append(f"  - `{media_type}`: " + render_schema(schema, 2).strip())
    return "\n".join(lines)


def spec_to_markdown(spec: dict, title: str = "") -> str:
    info    = spec.get("info", {})
    version = info.get("version", "")
    doc_title = title or info.get("title", "API Documentatie")

    md = [f"# {doc_title}", ""]
    if version:
        md.append(f"**Versie:** {version}  ")
    if info.get("description"):
        md.append(info["description"])
    md.append("")

    # Servers
    servers = spec.get("servers", [])
    if servers:
        md.append("## Servers\n")
        for s in servers:
            md.append(f"- `{s.get('url')}` — {s.get('description', '')}")
        md.append("")

    # Tags / groepen
    tag_ops: dict[str, list] = {}
    for path, path_item in spec.get("paths", {}).items():
        for method, op in path_item.items():
            if method in ("get", "post", "put", "patch", "delete", "head", "options"):
                tags = op.get("tags", ["Overig"])
                for tag in tags:
                    tag_ops.setdefault(tag, []).append((method, path, op))

    for tag, ops in tag_ops.items():
        md.append(f"---\n\n## {tag}\n")
        for method, path, op in ops:
            summary = op.get("summary", "")
            desc    = op.get("description", "")
            op_id   = op.get("operationId", "")

            md.append(f"### {method_badge(method)} `{path}`")
            if summary:
                md.append(f"\n**{summary}**")
            if op_id:
                md.append(f"\nOperation ID: `{op_id}`")
            if desc:
                md.append(f"\n{desc}")
            md.append("")

            params = op.get("parameters", [])
            if params:
                md.append(render_params(params, spec))
                md.append("")

            body = op.get("requestBody")
            if body:
                md.append(render_request_body(body, spec))
                md.append("")

            responses = op.get("responses", {})
            if responses:
                md.append(render_responses(responses, spec))
                md.append("")

    # Schemas/components
    schemas = spec.get("components", {}).get("schemas", {})
    if schemas:
        md.append("---\n\n## Data modellen\n")
        for name, schema in schemas.items():
            md.append(f"### `{name}`\n")
            if schema.get("description"):
                md.append(schema["description"] + "\n")
            rendered = render_schema(schema)
            if rendered:
                md.append(rendered)
            md.append("")

    return "\n".join(md)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenAPI spec → Markdown")
    parser.add_argument("source", help="URL of pad naar OpenAPI JSON/YAML")
    parser.add_argument("--out",   help="Output .md bestand (standaard: api_docs.md)")
    parser.add_argument("--title", default="", help="Titel (overschrijft spec-titel)")
    args = parser.parse_args()

    print(f"  [openapi] Laden: {args.source}")
    spec = load_spec(args.source)

    out = Path(args.out) if args.out else Path("api_docs.md")
    print(f"  [openapi] Converteren naar Markdown …")
    md = spec_to_markdown(spec, title=args.title)
    out.write_text(md, encoding="utf-8")
    print(f"✅  Markdown → {out}  ({len(md):,} tekens)")
