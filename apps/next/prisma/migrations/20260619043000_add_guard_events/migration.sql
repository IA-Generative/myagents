-- CreateTable
CREATE TABLE "ab_guard_events" (
    "id" UUID NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "user_id" TEXT,
    "route" TEXT NOT NULL,
    "stage" TEXT NOT NULL,
    "role" TEXT,
    "severity" TEXT NOT NULL,
    "signals" JSONB NOT NULL,

    CONSTRAINT "ab_guard_events_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "ab_guard_events_user_id_idx" ON "ab_guard_events"("user_id");

-- CreateIndex
CREATE INDEX "ab_guard_events_created_at_idx" ON "ab_guard_events"("created_at");
