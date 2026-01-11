# Silverbullet RAG

Deploys as a docker container that mounts the silverbullet space

## Space Parsing

File watches for changes. If possible, incremental reprocessing based only on files changed.

Use Markdown AST parsing using https://crates.io/crates/markdown

Chunk using headers to start

Vector embedding will be done with OpenAI.

The embedding model to use and the API key are in a `./.env` file that provides the following environment variables:

- `OPEN_AI_API_KEY`
- `EMBEDDING_MODEL`

## Database

Ladybug DB: https://github.com/LadybugDB/ladybug

https://docs.rs/lbug/latest/lbug/

On disk files https://docs.ladybugdb.com/developer-guide/files/

### Graph

Uses Silverbullet.md markdown wikilinks as edges.
Page tags are edges

The graph is just an index with metadata, including chunk boundaries, actual content retrieval can be by direct file access by chunk

## Model-Context-Protocol Server

Implement a [MCP server](https://modelcontextprotocol.io/docs/getting-started/intro) in Rust for RAG queries as tools

Uses the official Rust MCP SDK crates:

- [`rmcp`](https://crates.io/crates/rmcp)
- [`rmcp-macros`](https://crates.io/crates/rmcp-macros)

Runs a streamable HTTP Server using axum. [See example](https://github.com/modelcontextprotocol/rust-sdk/blob/main/examples/servers/src/counter_streamhttp.rs).

Exposes query tools for:

- Cypher query
- Keyword search: Page names, tag names
- Read page
- Update page

## Open WebUI

Implement a [Pipe](https://docs.openwebui.com/features/pipelines/pipes) to do RAG for Open WebUI calls. It can use the same MCP server as its source.

## Example Data

is loaded readonly at `./space` in the workspace.