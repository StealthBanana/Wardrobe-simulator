from app import app

if __name__ == "__main__":
    # Visit http://localhost:5000 in your browser after running this.
    # To access from another device on the same WiFi, use your local IP instead.
    app.run(debug=True, host="0.0.0.0", port=5000)
