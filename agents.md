# Multi-Agent Website Optimization System

## Architecture Overview

This system orchestrates multiple AI subagents, each with specific roles and preferred models.

## Subagents

### 1. 🎨 Design Agent (UI/UX)
- **Model**: Groq llama-3.3-70b-versatile
- **Role**: Visual design updates, component creation, modern UI generation
- **Tasks**: 
  - Create glassmorphism components
  - Generate Three.js visual effects
  - Design responsive layouts
  - Create color palettes

### 2. 💻 Development Agent (Frontend)
- **Model**: OpenRouter gpt-4o-mini
- **Role**: HTML/CSS/JavaScript implementation, debugging, optimization
- **Tasks**:
  - Write production code
  - Fix browser compatibility
  - Optimize performance
  - Add interactivity

### 3. 🔍 SEO Agent
- **Model**: DeepSeek deepseek-chat
- **Role**: Search optimization, metadata, content enhancement
- **Tasks**:
  - Keyword research
  - Meta tag optimization
  - Content analysis
  - Structured data

### 4. 🚀 Deployment Agent
- **Model**: z.ai GLM-5.2 (via ZAI)
- **Role**: GitHub deployment, CI/CD, domain management
- **Tasks**:
  - Git operations
  - GitHub Pages deployment
  - Domain configuration
  - SSL setup

### 5. 📊 Analytics Agent
- **Model**: OpenRouter anthropic/claude-3-haiku
- **Role**: Monitoring, metrics, performance tracking
- **Tasks**:
  - Page speed analysis
  - Error monitoring
  - User behavior tracking
  - Performance reports

### 6. 🔒 Security Agent
- **Model**: OpenRouter security models
- **Role**: Security scanning, vulnerability checks
- **Tasks**:
  - CSP headers
  - XSS prevention
  - Performance budget
  - Audit logs

## Agent Communication Flow

```
[Design Agent] → generates design spec
       ↓
[Development Agent] → implements the design
       ↓
[SEO Agent] → optimizes for search
       ↓
[Deployment Agent] → publishes to production
       ↓
[Analytics Agent] → monitors performance
       ↓
[Security Agent] → audits security
```

## Task Delegation Commands

- `/agents/design <task>` - Design Agent
- `/agents/dev <task>` - Development Agent  
- `/agents/seo <task>` - SEO Agent
- `/agents/deploy <task>` - Deployment Agent
- `/agents/analytics <task>` - Analytics Agent
- `/agents/security <task>` - Security Agent

## Model Selection Rules

1. **Design/Creative**: Groq models (fast, good for creativity)
2. **Code Implementation**: OpenRouter GPT-4o-mini (balanced)
3. **Search/Optimization**: DeepSeek (good for SEO research)
4. **Deployment**: z.ai GLM-5.2 (good at instructions)
5. **Monitoring**: Claude Haiku (concise reporting)
6. **Security**: Specialized security models

## Autonomy Settings

- Each agent runs for maximum 5 minutes per task
- Agents auto-retry on timeout with reduced complexity
- Failed agents escalate to main agent
- All agents report completion status to Telegram

## Current Active Sites

1. **hsndm.tech** - AI Automation Platform
2. **broastys** - Restaurant Site

## Status Files

Each agent maintains status at: `~/Agents/Logs/<agent-name>.log`