# data-insight-engine

## Usage Guide

### Step 1: Initial Setup

```bash
git clone <repository-url>
cd data-insight-engine
cp .env.example .env # Edit .env with your configuration
make build
```

### Step 2: Start the Stack

```bash
make up
```

### Step 3: Run Migrations

```bash
make migrate
```