import time
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    logger.info("Application started and running...")
    
    try:
        while True:
            time.sleep(60)  # Keep the container alive
    except KeyboardInterrupt:
        logger.info("Application stopped by user")