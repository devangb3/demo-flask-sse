import ast, logging, os
from kafka import KafkaConsumer, KafkaProducer
from json import loads, dumps
from flask import Flask, render_template
from flask_sse import sse
import threading

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
                try:
                    file_path = message.value.get('file_path')
                    if not file_path:
                        raise ValueError("No file_path provided in message")

                    possible_paths = [
                        file_path, 
                        os.path.join(os.getcwd(), file_path),
                        os.path.abspath(file_path)
                    ]

                    file_found = False
                    for path in possible_paths:
                        if os.path.isfile(path):
                            values = self.extract_variables_from_functions(path)
                            logging.info(f"Extracted variables: {values}")
                            
                            with app.app_context():
                                result = {
                                    'status': 'success',
                                    'session': message.value.get('session'),
                                    'data': values
                                }
                                self.producer.send('python_parser_out', value=result)
                                sse.publish({"message": values}, type='parser_update')
                            file_found = True
                            break

                    if not file_found:
                        raise FileNotFoundError(f"Could not find file in any location: {file_path}")

                except Exception as e:
                    error_msg = str(e)
                    logging.error(f"Error processing file: {error_msg}")
                    
                    with app.app_context():
                        error_result = {
                            'status': 'error',
                            'session': message.value.get('session'),
                            'error': error_msg
                        }
                        self.producer.send('python_parser_out', value=error_result)
                        sse.publish({"message": error_result}, type='parser_error')

        except Exception as e:
            logging.error(f"Fatal error in consumer: {str(e)}")
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
    parser_thread = threading.Thread(target=start_parser)
    parser_thread.daemon = True
    parser_thread.start()
    
    app.run(debug=True, threaded=True)