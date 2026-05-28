import usb_cdc

# Desactiva la consola (REPL) por USB
usb_cdc.enable(console=True, data=False)
