# app.py
import ast, logging
from kafka import KafkaConsumer, KafkaProducer
from json import loads, dumps
from flask import Flask, render_template, Response
from flask_sse import sse
import threading
from time import sleep

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

app = Flask(__name__)
app.config["REDIS_URL"] = "redis://localhost:6379"
app.register_blueprint(sse, url_prefix='/stream')

class PythonParser:
    def __init__(self):
        logging.info("Creating Python Parser Instance")
        self.consumer = KafkaConsumer(
            'python_parser_in',
            bootstrap_servers=['localhost:9093'],
            auto_offset_reset='earliest',
            enable_auto_commit=True,
            value_deserializer=lambda x: loads(x.decode('utf-8'))
        )
        logging.info("Consumer created")
        self.producer = KafkaProducer(
            bootstrap_servers=['localhost:9093'],
            value_serializer=lambda x: dumps(x).encode('utf-8'),
            security_protocol='PLAINTEXT'
        )
        logging.info("Producer created")

    def consume_kafka_messages(self):
        try:
            for message in self.consumer:
                logging.info(f"Received Kafka message: {message.value}")
                file_path = message.value['file_path']
                values = self.extract_variables_from_functions(file_path)
                logging.info(f"Extracted variables: {values}")
                # Send to both Kafka and SSE
                self.producer.send('python_parser_out', value=values)
                sse.publish({"data": values}, type='parser_update')
        except Exception as e:
            logging.error(str(e))
        finally:
            self.consumer.close()

    def extract_variables_from_functions(self, file_path):
        logging.info(f"Extracting variables from file: {file_path}")
        with open(file_path, "r") as file:
            source_code = file.read()
        logging.info("Source code read successfully")
        tree = ast.parse(source_code)
        logging.info("AST parsed successfully")
        
        results = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                function_name = node.name
                variables = set()
                
                for arg in node.args.args:
                    variables.add(arg.arg)
                
                for body_node in ast.walk(node):
                    if isinstance(body_node, ast.Assign):
                        for target in body_node.targets:
                            if isinstance(target, ast.Name):
                                variables.add(target.id)
                
                results.append({
                    "function_name": function_name,
                    "variables": list(variables)
                })
        
        return results

@app.route('/')
def index():
    return render_template('index.html')

def start_parser():
    parser = PythonParser()
    parser.consume_kafka_messages()

if __name__ == "__main__":
    # Start the Kafka consumer in a separate thread
    parser_thread = threading.Thread(target=start_parser)
    parser_thread.daemon = True
    parser_thread.start()
    
    app.run(debug=True, threaded=True)