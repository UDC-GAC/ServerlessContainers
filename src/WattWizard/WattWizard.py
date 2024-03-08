from flask import Flask
from src.WattWizard.parser import my_parser
from src.WattWizard.utils import create_models
from src.WattWizard.app.routes import routes

app = Flask(__name__)

app.register_blueprint(routes)

if __name__ == '__main__':
    # Parse arguments
    parser = my_parser.create_parser()
    args = parser.parse_args()
    my_parser.check_args(args)
    my_parser.set_args(args)

    # Create models and pretrain them (if specified)
    create_models.run()

    # Start Flask server
    app.run(host='0.0.0.0', port=7777)
