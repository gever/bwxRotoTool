PYTHON   := python3
VENV     := .venv
PIP      := $(VENV)/bin/pip
PYTHON_V := $(VENV)/bin/python

.PHONY: all setup run clean

all: setup

## Create the virtual environment and install all dependencies
setup: $(VENV)/bin/activate

$(VENV)/bin/activate: requirements.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt
	@touch $(VENV)/bin/activate
	@echo "✅  Environment ready. Run 'make run' to launch the tool."

## Launch the tool inside the venv
run: setup
	$(PYTHON_V) src/main.py

## Remove the virtual environment
clean:
	rm -rf $(VENV)
	@echo "🧹  Cleaned up .venv"
