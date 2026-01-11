# GitHub Actions Workflows

## Docker Build and Publish

The `docker-publish.yml` workflow automatically builds and publishes Docker images to GitHub Container Registry (GHCR).

### Triggers

- **Push to main branch**: Builds and pushes with `latest` and `main-<sha>` tags
- **Tagged releases** (e.g., `v1.0.0`): Builds and pushes with semantic version tags
- **Pull requests**: Builds only (doesn't push) for testing
- **Manual dispatch**: Can be triggered manually from Actions tab

### Multi-platform Builds

Images are built for both:
- `linux/amd64` (x86_64 - standard servers/desktops)
- `linux/arm64` (ARM - Raspberry Pi, Apple Silicon, etc.)

### Image Tags

When you push to main, the following tags are created:
- `ghcr.io/YOUR_USERNAME/silverbullet-rag:latest`
- `ghcr.io/YOUR_USERNAME/silverbullet-rag:main`
- `ghcr.io/YOUR_USERNAME/silverbullet-rag:main-abc1234` (commit SHA)

When you create a version tag (e.g., `git tag v1.2.3 && git push --tags`):
- `ghcr.io/YOUR_USERNAME/silverbullet-rag:v1.2.3`
- `ghcr.io/YOUR_USERNAME/silverbullet-rag:v1.2`
- `ghcr.io/YOUR_USERNAME/silverbullet-rag:v1`
- `ghcr.io/YOUR_USERNAME/silverbullet-rag:latest`

### Security Features

1. **Artifact Attestation**: Generates SLSA provenance for supply chain security
2. **Build Cache**: Uses GitHub Actions cache for faster builds
3. **Automatic Authentication**: Uses `GITHUB_TOKEN` (no manual setup needed)

### Making Images Private

By default, GHCR packages inherit repository visibility. To make images private:

1. **Private Repository**: Set repository to private (Settings → Danger Zone)
2. **Package Visibility**: Optionally override at package level:
   - Profile → Packages → silverbullet-rag → Package settings → Change visibility

### Pulling Private Images

To pull private images, authenticate with a Personal Access Token (PAT):

```bash
# Create PAT with read:packages scope
# GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)

# Login to GHCR
echo $YOUR_PAT | docker login ghcr.io -u YOUR_USERNAME --password-stdin

# Pull image
docker pull ghcr.io/YOUR_USERNAME/silverbullet-rag:latest
```

### Build Performance

- **First build**: ~5-10 minutes (compiles dependencies)
- **Subsequent builds**: ~2-3 minutes (uses cache)
- **Multi-platform**: Builds in parallel

### Monitoring Builds

1. Go to repository → Actions tab
2. Click on "Build and Push Docker Image" workflow
3. View individual workflow runs
4. Check build logs for any errors

### Troubleshooting

**Build fails on ARM64**:
- Some Python packages may not have ARM64 wheels
- Solution: Add platform-specific build args or exclude ARM64

**Permission denied when pushing**:
- Check repository settings → Actions → General
- Ensure "Read and write permissions" is enabled for `GITHUB_TOKEN`

**Image too large**:
- Check `.dockerignore` is properly configured
- Use multi-stage builds (already done)
- Remove unnecessary dependencies

### Manual Trigger

To manually trigger a build:

1. Go to Actions tab
2. Select "Build and Push Docker Image"
3. Click "Run workflow"
4. Select branch
5. Click "Run workflow"

### Customization

To modify the workflow:

1. Edit `.github/workflows/docker-publish.yml`
2. Common changes:
   - Add additional platforms: `platforms: linux/amd64,linux/arm64,linux/arm/v7`
   - Change branch triggers: `branches: [main, develop]`
   - Add build args: `build-args: |` section
   - Modify tags: `tags:` section in metadata step

### Best Practices

1. **Semantic Versioning**: Use `v1.0.0` format for release tags
2. **Test First**: Let PR builds complete before merging
3. **Monitor Sizes**: Keep eye on image size (current: ~500MB)
4. **Cache Strategy**: `mode=max` caches all layers for speed
5. **Security**: Regularly update action versions (dependabot recommended)

## Future Workflows

Additional workflows to consider:

- **Test Runner**: Run pytest on push/PR
- **Lint/Format**: Black, mypy, ruff checks
- **Security Scan**: Trivy/Snyk container scanning
- **Documentation**: Auto-generate and deploy docs
- **Release Notes**: Auto-generate changelog from commits
