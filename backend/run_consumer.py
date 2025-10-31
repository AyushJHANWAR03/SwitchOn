"""Run Kafka consumer service."""
import asyncio
import logging
from app.kafka_consumer import KafkaConsumerService

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Main entry point for consumer."""
    logger.info("Starting Kafka Consumer Service...")

    consumer = KafkaConsumerService()

    try:
        await consumer.run()
    except KeyboardInterrupt:
        logger.info("Consumer interrupted by user")
    except Exception as e:
        logger.error(f"Consumer error: {e}", exc_info=True)
    finally:
        await consumer.stop()
        logger.info("Consumer stopped")


if __name__ == "__main__":
    asyncio.run(main())
