# Agent Skills for isA_Cloud

This directory contains Agent Skills for the isA_Cloud platform - custom capabilities that extend Claude's functionality when working with this codebase.

## What are Agent Skills?

Agent Skills are modular capabilities that package instructions, metadata, and optional resources (scripts, templates) that Claude uses automatically when relevant. Skills follow the [Agent Skills open standard](https://agentskills.io).

**Key benefits for isA_Cloud:**
- **Specialize Claude** for Go microservices, Kubernetes deployments, and cloud-native workflows
- **Reduce repetition** by encoding isA_Cloud conventions, patterns, and domain knowledge
- **Compose capabilities** to build complex workflows specific to this platform

## How Skills Work

Skills leverage **progressive disclosure** - Claude loads information in stages:

1. **Metadata (always loaded)**: Skill name and description in system prompt
2. **Instructions (loaded when triggered)**: SKILL.md content when skill is activated
3. **Resources (loaded as needed)**: Additional files, scripts, templates referenced from SKILL.md

## Quick Start

### View Available Skills

```bash
# List all skills in this directory
ls -la .claude/skills/

# Ask Claude what skills are available
# Just ask: "What skills are available?"
```

### Use a Skill

**Two ways to invoke skills:**

1. **Let Claude decide** - Just work naturally. Claude automatically loads relevant skills:
   ```
   "Add a new gRPC service for user profiles"
   ```

2. **Invoke directly** - Use the `/skill-name` command:
   ```
   /create-grpc-service user-profile
   ```

## isA_Cloud Skills Directory Structure

```
.claude/skills/
├── README.md                          # ← This file
│
├── create-grpc-service/               # Scaffold new Go gRPC services
│   ├── SKILL.md
│   └── templates/
│       ├── service_template.go
│       ├── handler_template.go
│       └── repository_template.go
│
├── deploy-service/                    # Deploy services to Kubernetes
│   ├── SKILL.md
│   └── scripts/
│       ├── validate_manifest.sh
│       └── check_health.sh
│
├── implement-proto/                   # Implement gRPC handlers from .proto
│   ├── SKILL.md
│   └── examples/
│       └── handler_examples.md
│
├── cdd-workflow/                      # Contract-Driven Development workflow
│   ├── SKILL.md
│   └── templates/
│       ├── logic_contract_template.md
│       └── test_template.go
│
├── debug-service/                     # Debug running services
│   ├── SKILL.md
│   └── scripts/
│       └── collect_diagnostics.sh
│
├── add-feature/                       # Add features following isA patterns
│   ├── SKILL.md
│   └── reference/
│       ├── domain_layer.md
│       ├── service_layer.md
│       └── handler_layer.md
│
└── consul-operations/                 # Consul service discovery ops
    ├── SKILL.md
    └── scripts/
        ├── register_service.sh
        └── health_check.sh
```

## Creating Your First Skill

### Example: Create a "Review PR" Skill

```bash
# 1. Create skill directory
mkdir -p .claude/skills/review-pr

# 2. Create SKILL.md
cat > .claude/skills/review-pr/SKILL.md << 'EOF'
---
name: review-pr
description: Review pull requests for isA_Cloud. Check Go code quality, test coverage, proto definitions, Kubernetes manifests, and adherence to isA conventions. Use when reviewing PRs or when asked to check code changes.
---

# Pull Request Review for isA_Cloud

Review pull requests comprehensively following isA_Cloud standards.

## Review Checklist

### 1. Code Quality
- [ ] Go code follows [GO_MICROSERVICE_DEVELOPMENT_GUIDE.md](../../../docs/GO_MICROSERVICE_DEVELOPMENT_GUIDE.md)
- [ ] Clean Architecture layers are respected (domain → repository → service → handler)
- [ ] Error handling follows patterns (domain errors → gRPC status codes)
- [ ] Dependency injection via constructors

### 2. Contract-Driven Development
- [ ] Proto definitions in `api/proto/` are valid
- [ ] Logic contracts exist in `tests/contracts/{service}/logic_contract.md`
- [ ] Business rules are documented (BR-XXX)
- [ ] Edge cases are identified (EC-XXX)

### 3. Testing
- [ ] Unit tests exist with `//go:build unit` tag
- [ ] Test coverage for business logic >= 80%
- [ ] Integration tests for repository layer
- [ ] Test fixtures follow patterns in `tests/contracts/`

### 4. Kubernetes Manifests
- [ ] Deployments in `deployments/kubernetes/base/`
- [ ] Resource limits defined
- [ ] Health checks configured
- [ ] Service discovery (Consul) annotations present

### 5. Documentation
- [ ] README updated if needed
- [ ] PRD status updated in `docs/prd/`
- [ ] Architecture docs reflect changes

## Review Process

1. **Read the PR description**
2. **Check changed files** - identify affected layers
3. **Verify contracts** - proto, logic contracts, tests
4. **Review implementation** - domain → repository → service → handler
5. **Test coverage** - run `go test -cover`
6. **Kubernetes configs** - validate manifests
7. **Provide feedback** with specific file/line references

## Output Format

```markdown
## PR Review: {PR Title}

### ✅ Strengths
- List positive aspects

### ⚠️ Issues Found
- Issue 1 (file:line)
- Issue 2 (file:line)

### 💡 Suggestions
- Suggestion 1
- Suggestion 2

### 📋 Checklist Status
- [x] Code quality
- [ ] Contracts (missing logic_contract.md)
- [x] Tests
- [x] Kubernetes
- [ ] Documentation (README needs update)
```
EOF

# 3. Test the skill
# Ask Claude: "/review-pr"
```

## Skill Categories for isA_Cloud

### 1. Development Skills
- `create-grpc-service` - Scaffold new microservices
- `implement-proto` - Implement gRPC handlers
- `add-feature` - Add features following clean architecture
- `cdd-workflow` - Contract-Driven Development process

### 2. Infrastructure Skills
- `deploy-service` - Deploy to Kubernetes
- `configure-helm` - Create/update Helm charts
- `setup-argocd` - ArgoCD application definitions
- `consul-operations` - Service discovery management

### 3. Testing Skills
- `write-tests` - Generate tests following CDD
- `test-coverage` - Analyze and improve coverage
- `integration-tests` - Create integration tests
- `e2e-tests` - End-to-end test scenarios

### 4. Debugging Skills
- `debug-service` - Debug running services
- `analyze-logs` - Analyze service logs (Loki/Grafana)
- `trace-request` - Distributed tracing
- `performance-profile` - Profile Go services

### 5. Operations Skills
- `rollback-deployment` - Rollback using ArgoCD
- `scale-service` - Scale services
- `backup-data` - Backup/restore data
- `monitor-health` - Health check monitoring

### 6. Documentation Skills
- `document-service` - Generate service documentation
- `update-prd` - Update PRD with status
- `architecture-diagram` - Generate architecture diagrams
- `api-docs` - Generate API documentation

## Skill Structure

Every skill requires a `SKILL.md` file with YAML frontmatter:

```yaml
---
name: your-skill-name           # Lowercase, letters, numbers, hyphens only
description: Brief description of what this skill does and when to use it
context: fork                   # Optional: run in isolated subagent
agent: Explore                  # Optional: which subagent type
disable-model-invocation: true  # Optional: only manual invocation
user-invocable: true           # Optional: show in /menu
---

# Your Skill Name

## Instructions
Clear, step-by-step guidance for Claude to follow

## Examples
Concrete examples of using this skill
```

### Required Fields

- `name`: Max 64 chars, lowercase letters/numbers/hyphens only
- `description`: Max 1024 chars, describes what skill does **and when to use it**

### Optional Fields

- `context: fork` - Run in isolated subagent
- `agent: Explore` - Which subagent type (Explore, Plan, general-purpose)
- `disable-model-invocation: true` - Prevent auto-invocation, manual only
- `user-invocable: false` - Hide from menu, background knowledge only
- `allowed-tools: Read, Grep` - Restrict which tools skill can use

## Advanced Patterns

### Arguments and Variables

Skills support string substitution:

```yaml
---
name: deploy-environment
description: Deploy isA_Cloud to a specific environment
---

# Deploy to $ARGUMENTS Environment

Deploying to: $ARGUMENTS

Environment: $0          # First argument
Namespace: $1            # Second argument
Session: ${CLAUDE_SESSION_ID}  # Current session ID

Run deployment for **$ARGUMENTS** environment.
```

Usage:
```
/deploy-environment staging isa-cloud-staging
```

### Dynamic Context Injection

Run shell commands before Claude sees the skill content:

```yaml
---
name: check-service-status
description: Check status of isA_Cloud services
---

# Service Status Report

## Running Pods
!`kubectl get pods -n isa-cloud-staging`

## Consul Services
!`kubectl exec -n isa-cloud-staging consul-0 -- consul catalog services`

## APISIX Routes Count
!`kubectl exec -n isa-cloud-staging deploy/apisix -- curl -s http://localhost:9180/apisix/admin/routes -H "X-API-KEY: edd1c9f034335f136f87ad84b625c8f1" | jq '.list | length'`

Based on the above status, analyze the health of the system.
```

The `!`command`` syntax executes immediately and injects output into the skill content.

### Supporting Files

Keep `SKILL.md` focused, move details to separate files:

```
my-skill/
├── SKILL.md           # Main instructions (required)
├── reference.md       # Detailed reference (loaded when needed)
├── examples.md        # Usage examples
└── scripts/
    └── helper.sh      # Executable scripts
```

Reference from `SKILL.md`:

```markdown
## Additional Resources

- For complete API details, see [reference.md](reference.md)
- For usage examples, see [examples.md](examples.md)
- To analyze logs, run: `bash scripts/helper.sh`
```

## isA_Cloud Domain Knowledge

Skills should understand isA_Cloud specifics:

### Architecture Layers
1. **Transport Layer** - gRPC handlers (external interface)
2. **Service Layer** - Business logic (use cases)
3. **Repository Layer** - Data access (abstraction)
4. **Infrastructure Layer** - PostgreSQL, Redis, NATS

### Key Conventions
- **Protocol Buffers** in `api/proto/`
- **Clean Architecture** - dependency rule (outer → inner)
- **Contract-Driven Development** - contracts before implementation
- **Multi-tenant** - Organization and User IDs everywhere
- **Service Discovery** - Consul registration required
- **API Gateway** - APISIX for routing

### Directory Structure
```
isA_Cloud/
├── api/proto/           # gRPC contracts
├── cmd/{service}/       # Service entry points
├── internal/{service}/  # Service implementation
│   ├── domain/          # Entities, value objects
│   ├── repository/      # Data access
│   ├── service/         # Business logic
│   └── handler/         # gRPC handlers
├── deployments/         # Kubernetes configs
├── docs/                # Documentation
│   ├── domain/          # Business context
│   ├── prd/             # Requirements
│   └── design/          # Architecture
└── tests/contracts/     # Test contracts
```

## Best Practices

### Writing Effective Skills

1. **Be concise** - Assume Claude already knows Go and Kubernetes
2. **Be specific** - Include isA_Cloud conventions and patterns
3. **Provide examples** - Show concrete code snippets
4. **Reference docs** - Link to GO_MICROSERVICE_DEVELOPMENT_GUIDE.md, etc.
5. **Test thoroughly** - Use skills on real tasks before committing

### Description Guidelines

**Good description:**
```yaml
description: Create a new gRPC service following isA_Cloud patterns. Generates proto definitions, domain entities, repository, service, handler, and Kubernetes manifests. Use when scaffolding new microservices or adding major features.
```

**Bad description:**
```yaml
description: Helps create services
```

### Avoid Common Pitfalls

❌ **Don't** include Windows paths (`scripts\helper.py`)
✅ **Do** use forward slashes (`scripts/helper.py`)

❌ **Don't** assume packages are installed
✅ **Do** specify dependencies explicitly

❌ **Don't** make skills too general
✅ **Do** create focused, specific skills

❌ **Don't** over-explain basic concepts
✅ **Do** focus on isA_Cloud-specific knowledge

## Testing Skills

### Manual Testing
```bash
# 1. Create the skill
mkdir -p .claude/skills/test-skill
cat > .claude/skills/test-skill/SKILL.md << 'EOF'
---
name: test-skill
description: Test skill
---
Test content
EOF

# 2. Use the skill
# Ask Claude: "/test-skill"
# Or: "Do something that matches the description"

# 3. Verify behavior
# - Did Claude load the skill?
# - Did it follow the instructions?
# - Did it use supporting files correctly?
```

### Iterative Improvement

1. **Use in real work** - Apply skill to actual tasks
2. **Observe behavior** - Note where Claude struggles
3. **Refine instructions** - Make them clearer/more specific
4. **Update references** - Improve supporting files
5. **Test again** - Verify improvements work

## Skill Development Workflow

```
1. Identify Need
   └── What repetitive task could benefit from a skill?
   └── What domain knowledge should Claude have?

2. Create Skill Structure
   └── mkdir .claude/skills/{skill-name}
   └── Create SKILL.md with frontmatter

3. Write Instructions
   └── Focus on isA_Cloud specifics
   └── Reference existing docs
   └── Include examples

4. Add Supporting Files
   └── Scripts for automation
   └── Templates for generation
   └── Reference docs for details

5. Test Thoroughly
   └── Manual invocation (/skill-name)
   └── Auto-invocation (matching description)
   └── With arguments
   └── With supporting files

6. Iterate Based on Usage
   └── Use in real development
   └── Note issues
   └── Refine and improve

7. Document
   └── Add to this README
   └── Update skill descriptions
   └── Share with team
```

## Multiple Skills Requirements

For multiple related skills, consider:

### Skill Composition
Create focused skills that compose well:

```
# Base skill
/create-grpc-service → Scaffolds service structure

# Complementary skills
/implement-proto → Adds gRPC handlers
/write-tests → Adds test suite
/deploy-service → Deploys to Kubernetes
/document-service → Generates docs
```

### Skill Hierarchies
Create general and specialized variants:

```
# General
/add-feature → Generic feature addition

# Specialized
/add-crud-feature → CRUD-specific feature
/add-event-handler → Event-driven feature
/add-api-endpoint → API-specific feature
```

### Skill Preloading in Subagents
For complex workflows, preload multiple skills:

```yaml
# .claude/agents/full-service-dev.md
---
name: full-service-dev
skills:
  - create-grpc-service
  - implement-proto
  - write-tests
  - deploy-service
---

Create a complete gRPC service from scratch, including implementation, tests, and deployment.
```

## Related Documentation

| Document | Purpose |
|----------|---------|
| [GO_MICROSERVICE_DEVELOPMENT_GUIDE.md](../docs/GO_MICROSERVICE_DEVELOPMENT_GUIDE.md) | Go service development patterns |
| [cdd_guide.md](../docs/cdd_guide.md) | Contract-Driven Development |
| [cicd.md](../docs/cicd.md) | CI/CD workflows |
| [current_status.md](../docs/current_status.md) | Current platform status |

## Resources

- **Official Agent Skills Docs**: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/overview
- **Claude Code Skills Docs**: https://code.claude.com/docs/en/skills
- **Best Practices**: https://platform.claude.com/docs/en/agents-and-tools/agent-skills/best-practices
- **Agent Skills Standard**: https://agentskills.io

---

**Version**: 1.0.0  
**Last Updated**: 2026-02-04  
**Maintainer**: isA Cloud Team

## Getting Help

- Ask Claude: "What skills are available?"
- Check skill descriptions: `cat .claude/skills/{skill-name}/SKILL.md`
- Read official docs: https://code.claude.com/docs/en/skills
- Create issues for skill improvements in the isA_Cloud repo
