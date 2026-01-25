// Package version provides version information for silverbullet-rag.
package version

// Version is the current version of silverbullet-rag.
// This should match the version in pyproject.toml.
// It can be overridden at build time with:
//
//	go build -ldflags "-X github.com/boblangley/silverbullet-rag/internal/version.Version=x.y.z"
var Version = "0.1.0"

// Name is the application name.
const Name = "silverbullet-rag"
