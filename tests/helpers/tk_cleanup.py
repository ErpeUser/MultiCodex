"""Dispose only the test root's interpreter callbacks between native cases."""
def close_test_app(app):
    app.closing = True
    app._shutdown()
    for identity in app.tk.call('after', 'info'):
        app.tk.call('after', 'cancel', identity)
