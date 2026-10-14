-- CreateEnum
CREATE TYPE "Visibility" AS ENUM ('private', 'community', 'ministry');

-- CreateEnum
CREATE TYPE "AgentStatus" AS ENUM ('draft', 'published', 'submitted', 'validated', 'archived');

-- CreateTable
CREATE TABLE "ab_agents" (
    "id" UUID NOT NULL,
    "owui_model_id" TEXT NOT NULL,
    "creator_id" UUID NOT NULL,
    "creator_direction" TEXT,
    "visibility" "Visibility" NOT NULL DEFAULT 'private',
    "status" "AgentStatus" NOT NULL DEFAULT 'draft',
    "category" TEXT[],
    "tags" TEXT[],
    "version" INTEGER NOT NULL DEFAULT 1,
    "parent_agent_id" UUID,
    "quality_score" DECIMAL(3,2),
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "ab_agents_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ab_agent_versions" (
    "id" UUID NOT NULL,
    "agent_id" UUID NOT NULL,
    "version" INTEGER NOT NULL,
    "config_snapshot" JSONB NOT NULL,
    "changelog" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ab_agent_versions_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ab_ratings" (
    "id" UUID NOT NULL,
    "agent_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "score" SMALLINT NOT NULL,
    "comment" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ab_ratings_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ab_usage_stats" (
    "id" UUID NOT NULL,
    "agent_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "conversations_count" INTEGER NOT NULL DEFAULT 0,
    "last_used_at" TIMESTAMPTZ,
    "tokens_consumed" BIGINT NOT NULL DEFAULT 0,

    CONSTRAINT "ab_usage_stats_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ab_favorites" (
    "user_id" UUID NOT NULL,
    "agent_id" UUID NOT NULL,
    "folder" TEXT NOT NULL DEFAULT 'default',

    CONSTRAINT "ab_favorites_pkey" PRIMARY KEY ("user_id","agent_id")
);

-- CreateTable
CREATE TABLE "ab_si_connectors" (
    "id" UUID NOT NULL,
    "agent_id" UUID NOT NULL,
    "connector_type" TEXT NOT NULL,
    "config" JSONB NOT NULL,
    "credentials_vault_ref" TEXT,
    "enabled" BOOLEAN NOT NULL DEFAULT true,

    CONSTRAINT "ab_si_connectors_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ab_conversations" (
    "id" UUID NOT NULL,
    "agent_id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "title" TEXT,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL,

    CONSTRAINT "ab_conversations_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ab_conversation_messages" (
    "id" UUID NOT NULL,
    "conversation_id" UUID NOT NULL,
    "role" TEXT NOT NULL,
    "content" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "ab_conversation_messages_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "ab_mail_indexes" (
    "id" UUID NOT NULL,
    "user_id" UUID NOT NULL,
    "owui_knowledge_id" TEXT,
    "folders_scope" TEXT[],
    "last_sync_at" TIMESTAMPTZ,
    "sync_status" TEXT NOT NULL DEFAULT 'idle',
    "email_count" INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT "ab_mail_indexes_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "ab_agents_creator_id_idx" ON "ab_agents"("creator_id");

-- CreateIndex
CREATE INDEX "ab_agents_visibility_status_idx" ON "ab_agents"("visibility", "status");

-- CreateIndex
CREATE UNIQUE INDEX "ab_agent_versions_agent_id_version_key" ON "ab_agent_versions"("agent_id", "version");

-- CreateIndex
CREATE UNIQUE INDEX "ab_ratings_agent_id_user_id_key" ON "ab_ratings"("agent_id", "user_id");

-- CreateIndex
CREATE INDEX "ab_conversations_user_id_agent_id_idx" ON "ab_conversations"("user_id", "agent_id");

-- AddForeignKey
ALTER TABLE "ab_agent_versions" ADD CONSTRAINT "ab_agent_versions_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "ab_agents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ab_ratings" ADD CONSTRAINT "ab_ratings_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "ab_agents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ab_usage_stats" ADD CONSTRAINT "ab_usage_stats_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "ab_agents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ab_favorites" ADD CONSTRAINT "ab_favorites_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "ab_agents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ab_si_connectors" ADD CONSTRAINT "ab_si_connectors_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "ab_agents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ab_conversations" ADD CONSTRAINT "ab_conversations_agent_id_fkey" FOREIGN KEY ("agent_id") REFERENCES "ab_agents"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "ab_conversation_messages" ADD CONSTRAINT "ab_conversation_messages_conversation_id_fkey" FOREIGN KEY ("conversation_id") REFERENCES "ab_conversations"("id") ON DELETE CASCADE ON UPDATE CASCADE;
