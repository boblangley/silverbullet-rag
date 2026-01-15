# gRPC Client Examples

The Silverbullet RAG gRPC server provides fast, binary-protocol access to search and query functionality. This is ideal for Silverbullet hooks and performance-critical integrations.

## Server Details

- **Port**: 50051
- **Protocol**: gRPC with Protocol Buffers
- **Proto file**: `server/grpc/rag.proto`

## Available RPCs

| RPC | Request | Response | Description |
|-----|---------|----------|-------------|
| `Query` | `QueryRequest` | `QueryResponse` | Execute Cypher queries |
| `Search` | `SearchRequest` | `SearchResponse` | BM25 keyword search |
| `SemanticSearch` | `SemanticSearchRequest` | `SemanticSearchResponse` | Vector similarity search |
| `HybridSearch` | `HybridSearchRequest` | `HybridSearchResponse` | Combined keyword + semantic |
| `ReadPage` | `ReadPageRequest` | `ReadPageResponse` | Read a page from the space |
| `ProposeChange` | `ProposeChangeRequest` | `ProposeChangeResponse` | Propose a change (creates a proposal for user review) |
| `ListProposals` | `ListProposalsRequest` | `ListProposalsResponse` | List proposals by status |
| `WithdrawProposal` | `WithdrawProposalRequest` | `WithdrawProposalResponse` | Withdraw a pending proposal |

## Proto Definition

```protobuf
syntax = "proto3";
package silverbullet_rag;

service RAGService {
  rpc Query(QueryRequest) returns (QueryResponse);
  rpc Search(SearchRequest) returns (SearchResponse);
  rpc SemanticSearch(SemanticSearchRequest) returns (SemanticSearchResponse);
  rpc HybridSearch(HybridSearchRequest) returns (HybridSearchResponse);
  rpc ReadPage(ReadPageRequest) returns (ReadPageResponse);
  rpc ProposeChange(ProposeChangeRequest) returns (ProposeChangeResponse);
  rpc ListProposals(ListProposalsRequest) returns (ListProposalsResponse);
  rpc WithdrawProposal(WithdrawProposalRequest) returns (WithdrawProposalResponse);
}

message SemanticSearchRequest {
  string query = 1;
  int32 limit = 2;
  repeated string filter_tags = 3;
  repeated string filter_pages = 4;
}

message HybridSearchRequest {
  string query = 1;
  int32 limit = 2;
  repeated string filter_tags = 3;
  repeated string filter_pages = 4;
  string fusion_method = 5;  // "rrf" or "weighted"
  float semantic_weight = 6;
  float keyword_weight = 7;
}

message ProposeChangeRequest {
  string target_page = 1;
  string content = 2;
  string title = 3;
  string description = 4;
}

message ProposeChangeResponse {
  bool success = 1;
  string error = 2;
  string proposal_path = 3;
  bool is_new_page = 4;
  string message = 5;
}
```

---

## Python

### Installation

```bash
pip install grpcio grpcio-tools
```

### Generate Stubs (if needed)

```bash
python -m grpc_tools.protoc \
  -I. \
  --python_out=. \
  --grpc_python_out=. \
  rag.proto
```

### Client Example

```python
import grpc
import json
import rag_pb2
import rag_pb2_grpc

def main():
    # Connect to server
    channel = grpc.insecure_channel('localhost:50051')
    stub = rag_pb2_grpc.RAGServiceStub(channel)

    # Keyword Search
    search_response = stub.Search(rag_pb2.SearchRequest(
        keyword="database"
    ))
    if search_response.success:
        results = json.loads(search_response.results_json)
        print(f"Found {len(results)} results")
        for r in results[:3]:
            print(f"  - {r['file_path']}: {r['header']}")

    # Semantic Search
    semantic_response = stub.SemanticSearch(rag_pb2.SemanticSearchRequest(
        query="How do I configure authentication?",
        limit=5,
        filter_tags=["config", "auth"]
    ))
    if semantic_response.success:
        results = json.loads(semantic_response.results_json)
        for r in results:
            print(f"Score: {r['similarity']:.3f} - {r['file_path']}")

    # Hybrid Search
    hybrid_response = stub.HybridSearch(rag_pb2.HybridSearchRequest(
        query="database optimization",
        limit=10,
        fusion_method="rrf",
        semantic_weight=0.6,
        keyword_weight=0.4
    ))
    if hybrid_response.success:
        results = json.loads(hybrid_response.results_json)
        for r in results:
            print(f"Combined score: {r['score']:.3f} - {r['header']}")

    # Cypher Query
    query_response = stub.Query(rag_pb2.QueryRequest(
        cypher_query="MATCH (c:Chunk)-[:TAGGED]->(t:Tag) RETURN t.name, COUNT(c) AS count ORDER BY count DESC LIMIT 10"
    ))
    if query_response.success:
        results = json.loads(query_response.results_json)
        print("Top tags:", results)

if __name__ == "__main__":
    main()
```

---

## TypeScript / Node.js

### Installation

```bash
npm install @grpc/grpc-js @grpc/proto-loader
```

### Client Example

```typescript
import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import * as path from 'path';

const PROTO_PATH = path.resolve(__dirname, 'rag.proto');

const packageDefinition = protoLoader.loadSync(PROTO_PATH, {
  keepCase: true,
  longs: String,
  enums: String,
  defaults: true,
  oneofs: true,
});

const ragProto = grpc.loadPackageDefinition(packageDefinition) as any;

async function main() {
  const client = new ragProto.silverbullet_rag.RAGService(
    'localhost:50051',
    grpc.credentials.createInsecure()
  );

  // Keyword Search
  client.Search({ keyword: 'database' }, (err: Error, response: any) => {
    if (err) {
      console.error('Search error:', err);
      return;
    }
    if (response.success) {
      const results = JSON.parse(response.results_json);
      console.log(`Found ${results.length} results`);
      results.slice(0, 3).forEach((r: any) => {
        console.log(`  - ${r.file_path}: ${r.header}`);
      });
    }
  });

  // Semantic Search
  client.SemanticSearch(
    {
      query: 'How do I configure authentication?',
      limit: 5,
      filter_tags: ['config'],
    },
    (err: Error, response: any) => {
      if (err) {
        console.error('Semantic search error:', err);
        return;
      }
      if (response.success) {
        const results = JSON.parse(response.results_json);
        results.forEach((r: any) => {
          console.log(`Score: ${r.similarity.toFixed(3)} - ${r.file_path}`);
        });
      }
    }
  );

  // Hybrid Search
  client.HybridSearch(
    {
      query: 'database optimization',
      limit: 10,
      fusion_method: 'rrf',
      semantic_weight: 0.6,
      keyword_weight: 0.4,
    },
    (err: Error, response: any) => {
      if (err) {
        console.error('Hybrid search error:', err);
        return;
      }
      if (response.success) {
        const results = JSON.parse(response.results_json);
        results.forEach((r: any) => {
          console.log(`Score: ${r.score.toFixed(3)} - ${r.header}`);
        });
      }
    }
  );
}

main();
```

---

## Rust

### Cargo.toml

```toml
[dependencies]
tonic = "0.10"
prost = "0.12"
tokio = { version = "1", features = ["full"] }
serde_json = "1.0"

[build-dependencies]
tonic-build = "0.10"
```

### build.rs

```rust
fn main() -> Result<(), Box<dyn std::error::Error>> {
    tonic_build::compile_protos("rag.proto")?;
    Ok(())
}
```

### Client Example

```rust
use tonic::transport::Channel;

pub mod rag {
    tonic::include_proto!("silverbullet_rag");
}

use rag::rag_service_client::RagServiceClient;
use rag::{SearchRequest, SemanticSearchRequest, HybridSearchRequest, QueryRequest};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let channel = Channel::from_static("http://localhost:50051")
        .connect()
        .await?;

    let mut client = RagServiceClient::new(channel);

    // Keyword Search
    let search_response = client
        .search(SearchRequest {
            keyword: "database".to_string(),
        })
        .await?;

    let response = search_response.into_inner();
    if response.success {
        let results: serde_json::Value = serde_json::from_str(&response.results_json)?;
        println!("Search results: {:?}", results);
    }

    // Semantic Search
    let semantic_response = client
        .semantic_search(SemanticSearchRequest {
            query: "How do I configure authentication?".to_string(),
            limit: 5,
            filter_tags: vec!["config".to_string()],
            filter_pages: vec![],
        })
        .await?;

    let response = semantic_response.into_inner();
    if response.success {
        let results: serde_json::Value = serde_json::from_str(&response.results_json)?;
        println!("Semantic results: {:?}", results);
    }

    // Hybrid Search
    let hybrid_response = client
        .hybrid_search(HybridSearchRequest {
            query: "database optimization".to_string(),
            limit: 10,
            filter_tags: vec![],
            filter_pages: vec![],
            fusion_method: "rrf".to_string(),
            semantic_weight: 0.6,
            keyword_weight: 0.4,
        })
        .await?;

    let response = hybrid_response.into_inner();
    if response.success {
        let results: serde_json::Value = serde_json::from_str(&response.results_json)?;
        println!("Hybrid results: {:?}", results);
    }

    Ok(())
}
```

---

## Go

### Installation

```bash
go install google.golang.org/protobuf/cmd/protoc-gen-go@latest
go install google.golang.org/grpc/cmd/protoc-gen-go-grpc@latest
```

### Generate Stubs

```bash
protoc --go_out=. --go-grpc_out=. rag.proto
```

### Client Example

```go
package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"

	pb "your-module/rag"
	"google.golang.org/grpc"
	"google.golang.org/grpc/credentials/insecure"
)

func main() {
	conn, err := grpc.Dial("localhost:50051", grpc.WithTransportCredentials(insecure.NewCredentials()))
	if err != nil {
		log.Fatalf("Failed to connect: %v", err)
	}
	defer conn.Close()

	client := pb.NewRAGServiceClient(conn)
	ctx := context.Background()

	// Keyword Search
	searchResp, err := client.Search(ctx, &pb.SearchRequest{
		Keyword: "database",
	})
	if err != nil {
		log.Printf("Search error: %v", err)
	} else if searchResp.Success {
		var results []map[string]interface{}
		json.Unmarshal([]byte(searchResp.ResultsJson), &results)
		fmt.Printf("Found %d results\n", len(results))
	}

	// Semantic Search
	semanticResp, err := client.SemanticSearch(ctx, &pb.SemanticSearchRequest{
		Query:      "How do I configure authentication?",
		Limit:      5,
		FilterTags: []string{"config"},
	})
	if err != nil {
		log.Printf("Semantic search error: %v", err)
	} else if semanticResp.Success {
		var results []map[string]interface{}
		json.Unmarshal([]byte(semanticResp.ResultsJson), &results)
		for _, r := range results {
			fmt.Printf("Score: %.3f - %s\n", r["similarity"], r["file_path"])
		}
	}

	// Hybrid Search
	hybridResp, err := client.HybridSearch(ctx, &pb.HybridSearchRequest{
		Query:          "database optimization",
		Limit:          10,
		FusionMethod:   "rrf",
		SemanticWeight: 0.6,
		KeywordWeight:  0.4,
	})
	if err != nil {
		log.Printf("Hybrid search error: %v", err)
	} else if hybridResp.Success {
		var results []map[string]interface{}
		json.Unmarshal([]byte(hybridResp.ResultsJson), &results)
		for _, r := range results {
			fmt.Printf("Score: %.3f - %s\n", r["score"], r["header"])
		}
	}
}
```

---

## C# / .NET

### Installation

```bash
dotnet add package Grpc.Net.Client
dotnet add package Google.Protobuf
dotnet add package Grpc.Tools
```

### .csproj Configuration

```xml
<ItemGroup>
  <Protobuf Include="rag.proto" GrpcServices="Client" />
</ItemGroup>
```

### Client Example

```csharp
using Grpc.Net.Client;
using SilverbulletRag;
using System.Text.Json;

class Program
{
    static async Task Main(string[] args)
    {
        using var channel = GrpcChannel.ForAddress("http://localhost:50051");
        var client = new RAGService.RAGServiceClient(channel);

        // Keyword Search
        var searchResponse = await client.SearchAsync(new SearchRequest
        {
            Keyword = "database"
        });

        if (searchResponse.Success)
        {
            var results = JsonSerializer.Deserialize<List<Dictionary<string, object>>>(
                searchResponse.ResultsJson);
            Console.WriteLine($"Found {results?.Count} results");
        }

        // Semantic Search
        var semanticRequest = new SemanticSearchRequest
        {
            Query = "How do I configure authentication?",
            Limit = 5
        };
        semanticRequest.FilterTags.Add("config");

        var semanticResponse = await client.SemanticSearchAsync(semanticRequest);
        if (semanticResponse.Success)
        {
            var results = JsonSerializer.Deserialize<List<Dictionary<string, object>>>(
                semanticResponse.ResultsJson);
            foreach (var r in results ?? new List<Dictionary<string, object>>())
            {
                Console.WriteLine($"Score: {r["similarity"]} - {r["file_path"]}");
            }
        }

        // Hybrid Search
        var hybridRequest = new HybridSearchRequest
        {
            Query = "database optimization",
            Limit = 10,
            FusionMethod = "rrf",
            SemanticWeight = 0.6f,
            KeywordWeight = 0.4f
        };

        var hybridResponse = await client.HybridSearchAsync(hybridRequest);
        if (hybridResponse.Success)
        {
            var results = JsonSerializer.Deserialize<List<Dictionary<string, object>>>(
                hybridResponse.ResultsJson);
            foreach (var r in results ?? new List<Dictionary<string, object>>())
            {
                Console.WriteLine($"Score: {r["score"]} - {r["header"]}");
            }
        }
    }
}
```

---

## Error Handling

All responses include:
- `success`: Boolean indicating if the operation succeeded
- `error`: Error message if `success` is false
- `results_json`: JSON-encoded results if `success` is true

Always check `success` before parsing `results_json`:

```python
response = stub.Search(request)
if not response.success:
    print(f"Error: {response.error}")
    return

results = json.loads(response.results_json)
```

## Connection Options

### With TLS

```python
# Python with TLS
credentials = grpc.ssl_channel_credentials()
channel = grpc.secure_channel('your-server:50051', credentials)
```

### With Timeout

```python
# Python with timeout
response = stub.Search(request, timeout=10.0)  # 10 second timeout
```

### Retry Logic

```python
import grpc
from grpc import RpcError

def search_with_retry(stub, keyword, max_retries=3):
    for attempt in range(max_retries):
        try:
            return stub.Search(rag_pb2.SearchRequest(keyword=keyword))
        except RpcError as e:
            if e.code() == grpc.StatusCode.UNAVAILABLE and attempt < max_retries - 1:
                time.sleep(2 ** attempt)  # Exponential backoff
                continue
            raise
```
