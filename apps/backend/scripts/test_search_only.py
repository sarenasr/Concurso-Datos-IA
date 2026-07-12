"""Quick diagnostic: test search_catalog for the problematic question."""

from app.agents.tools import search_catalog

questions = [
    ("Cuantos medicamentos vigentes hay?", "i7cb-raxc"),
    ("contratos publicos Medellin 2025", "jbjy-vk9h"),
    ("casos COVID ultima semana", "gt2j-8ykr"),
    ("TRM promedio ultimo mes", "mcec-87by"),
    ("beneficiarios Familias en Accion Antioquia", "xfif-myr2"),
]

print("=" * 80)
print("Search diagnostic")
print("=" * 80)

for q, expected in questions:
    print(f"\nQ: {q}")
    print(f"Expected: {expected}")
    results = search_catalog(q, k=5)
    for i, r in enumerate(results, 1):
        marker = " <-- MATCH" if r["id"] == expected else ""
        print(
            f"  {i}. {r['id']} | score={r.get('score', 0):.3f} | {(r.get('name') or '')[:50]}{marker}"
        )
    top = results[0]["id"] if results else None
    status = "PASS" if top == expected else "FAIL"
    print(f"  -> {status} (top={top})")
