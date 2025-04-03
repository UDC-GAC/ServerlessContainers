from flask import Flask
from src.WattWizard.config.MyConfig import MyConfig
from src.WattWizard.parser.CLIParser import CLIParser
from src.WattWizard.parser.ConfigFileParser import ConfigFileParser
from src.WattWizard.parser.ArgsManager import ArgsManager
from src.WattWizard.utils.ModelBuilder import ModelBuilder
from src.WattWizard.app.routes import routes

app = Flask(__name__)

app.register_blueprint(routes)

if __name__ == '__main__':
    # Parse arguments from CLI
    cli_parser = CLIParser()
    cli_args = cli_parser.parse_args()

    # Parse arguments from configuration file
    config_file_parser = ConfigFileParser()
    config_file_args = config_file_parser.parse_args()

    # Process and validate arguments
    args_manager = ArgsManager(cli_args, config_file_args)
    args_manager.manage_args()
    args_manager.validate_args()

    # Build, train and test models
    model_builder = ModelBuilder()
    model_builder.build_models()

    # Start Flask server
    if MyConfig.get_instance().get_argument("server_mode"):
        app.run(host='0.0.0.0', port=7777)
