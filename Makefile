IMAGE = deanqrunpod/tetrarc
TAG = latest
FULL_IMAGE = $(IMAGE):$(TAG)

.PHONY: setup

# Check if 'uv' is installed
ifeq (, $(shell which uv))
$(error "uv is not installed. Please install it before running this Makefile.")
endif

setup:
	uv sync
	git submodule init
	git submodule update
	cp tetra-rp/src/tetra_rp/protos/remote_execution.py .

build: setup
	docker buildx build \
	--no-cache \
	--platform linux/amd64 \
	-t $(FULL_IMAGE) \
	. --load

build-cpu: setup
	docker buildx build \
	--no-cache \
	--platform linux/amd64 \
	-t $(IMAGE)-cpu:$(TAG) \
	-f Dockerfile-cpu \
	. --load

push:
	docker push $(FULL_IMAGE)

push-cpu:
	docker push $(IMAGE)-cpu:$(TAG)

dev:
	uv sync --all-groups
