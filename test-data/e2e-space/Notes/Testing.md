---
tags: note, testing
created: 2025-01-15
---

# Testing Notes

## Unit Tests

Run with pytest:
```bash
python -m pytest tests/ -v
```

## Integration Tests

Integration tests require Docker:
```bash
./scripts/run-integration-tests.sh
```

## E2E Tests

End-to-end tests run with a real Silverbullet instance:
```bash
RUN_E2E_TESTS=true ./scripts/run-integration-tests.sh --e2e
```

## Test Coverage

Key areas to test:
- Search functionality (keyword, semantic, hybrid)
- Graph queries (Cypher)
- Proposal workflow (create, list, accept, reject)
- Library installation

## Related

- [[Projects/Silverbullet-RAG]]
