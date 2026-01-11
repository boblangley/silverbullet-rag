# Silverbullet RAG

I am using Silverbullet as my “second brain”. I need a way to utilize this with AI coding assistants like Claude.

This means processing the Silverbullet space and making it available for queries, as well as allowing the AI assistant to make updates and add documents.

I want to both create a graph and allow for keyword and semantic search of the space.

I am running Silverbullet on a container, with the space mounted as a volume. This parser and server should also run in a container with the same volume mounted.

So this can be easily plugged in to coding assistants, it should be exposed as a Model-Context-Protocol (MCP) server.

A gRPC endpoint and client (Python) should also be provided to facilitate fast low-level access for things like hooks.

The graph and indexes should be updated as files change on disk. The graph db should not store the _contents_ of the space, but pointers to pages and/or page sections.

The system should be written in Python.

## Space Parsing

File watches for changes.

Process the changed file using a Markdown AST parser https://github.com/executablebooks/markdown-it-py

We should decide when/how to chunk. This is an open question for the spec. Options:

- Whole pages. Most pages are not that big.
- Break down by headings, at least `##` headings.
- Use LLM assisted smart chunking. Have an LLM review the page and decide on chunking strategy. Chunks could be delimited by space-lua comments e.g. `${"" --[[<CHUNK ID>]]}`

It may actually be best to decide on a case-by-case basis or with a simple set of rules.

- LadyBug DB
  - Graph:
    - `[[]]` Silverbullet “wikilinks” are edges to other documents.
    - Pages with `tags` front matter should have edges to other documents with those tags.
    - Just an index. Metadata points to blobs (or chunks) on disk
  - Embedding
    - Remove any Silverbullet syntax noise, e.g. attributes
  - Keyword BM25 Ranking. Tags are good keywords. Also technical terms.
- Duck DB?
  - Are tags a good use of this?

## Database(s)

### Ladybug DB
https://github.com/LadybugDB/ladybug
https://docs.ladybugdb.com/client-apis/python/
https://api-docs.ladybugdb.com/python/real_ladybug
On disk files https://docs.ladybugdb.com/developer-guide/files/

## Model-Context-Protocol Server

Implement a [MCP server](https://modelcontextprotocol.io/docs/getting-started/intro) in Rust for RAG queries as tools

Uses the official Python MCP SDK https://github.com/modelcontextprotocol/python-sdk

Runs a streamable HTTP Server using axum. https://github.com/modelcontextprotocol/python-sdk?tab=readme-ov-file#streamable-http-transport

Exposes query tools for:

- Cypher query
- Keyword search: Page names, tag names
- Read page
- Update page

## Open WebUI

Implement a [Pipe](https://docs.openwebui.com/features/pipelines/pipes) to do RAG for Open WebUI calls. It can use the same MCP server as its source.
## Example Data

is loaded readonly at `./space` in the workspace.