import os
from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .db import init_db
from .services import AirportService, ConflictError, ValidationError


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_mapping(
        DATABASE=os.environ.get(
            "AIRPORT_DATABASE",
            str(Path(app.instance_path) / "airport_operations.sqlite3"),
        )
    )
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    init_db(app.config["DATABASE"])

    def service():
        return AirportService(app.config["DATABASE"])

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/dashboard")
    def dashboard():
        return jsonify(service().dashboard())

    @app.get("/api/options")
    def options():
        return jsonify(service().options())

    @app.get("/api/gates")
    def gates():
        return jsonify(service().gates())

    @app.get("/api/flights")
    def flights():
        return jsonify(service().list_flights(request.args))

    @app.post("/api/flights")
    def create_flight():
        data = request.get_json(silent=True) or {}
        return jsonify(service().create_flight(data)), 201

    @app.patch("/api/flights/<int:flight_id>/status")
    def update_status(flight_id):
        data = request.get_json(silent=True) or {}
        return jsonify(service().update_status(flight_id, data.get("status", "")))

    @app.post("/api/flights/<int:flight_id>/assignments")
    def assign_gate(flight_id):
        data = request.get_json(silent=True) or {}
        return jsonify(service().assign_gate(flight_id, data.get("gate_id"))), 201

    @app.post("/api/flights/<int:flight_id>/delays")
    def record_delay(flight_id):
        data = request.get_json(silent=True) or {}
        return jsonify(service().record_delay(flight_id, data)), 201

    @app.errorhandler(ValidationError)
    @app.errorhandler(ConflictError)
    def handle_domain_error(error):
        status = 409 if isinstance(error, ConflictError) else 400
        return jsonify({"error": str(error)}), status

    @app.errorhandler(404)
    def not_found(_error):
        return jsonify({"error": "未找到请求的资源"}), 404

    @app.errorhandler(500)
    def internal_error(_error):
        return jsonify({"error": "服务器处理请求时发生错误"}), 500

    return app

