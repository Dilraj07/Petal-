import os
import json
import redis
import structlog
from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Setup Celery
app = Celery("petal_tasks", broker=REDIS_URL, backend=REDIS_URL)
app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# Setup Redis client for PubSub
redis_client = redis.Redis.from_url(REDIS_URL)

def redis_pubsub_processor(logger, log_method, event_dict):
    """
    If a celery task_id is present in the context, publish the log dict to Redis PubSub.
    """
    task_id = event_dict.get("task_id")
    if task_id:
        channel = f"petal_logs_{task_id}"
        # Convert event_dict to JSON string
        try:
            msg = json.dumps(event_dict)
            redis_client.publish(channel, msg)
        except Exception as e:
            logger.warning(f"Non-critical error during event serialization: {e}")
    return event_dict

# Configure structlog globally
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        redis_pubsub_processor,
        structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(structlog.PrintLogger),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

@app.task(bind=True)
def run_compile_pipeline(self, file_path, optimize, policy, collector, tdp, runs, emit_report=False):
    """
    Celery task that invokes the core Petal compiler pipeline.
    """
    import structlog.contextvars
    structlog.contextvars.bind_contextvars(task_id=self.request.id)
    
    logger = structlog.get_logger("tasks")
    logger.info("Task started", file_path=file_path, policy=policy, collector=collector)
    
    # We will import main.run_pipeline and call it directly.
    # main.py needs to be refactored to expose run_pipeline().
    from main import run_pipeline
    
    try:
        metadata = run_pipeline(
            file_path=file_path,
            optimize=optimize,
            policy=policy,
            collector=collector,
            tdp_arg=tdp,
            runs=runs,
            emit_report=emit_report
        )
        logger.info("Task completed successfully")
        return metadata
    except Exception as e:
        logger.exception("Pipeline failed", error=str(e))
        raise
