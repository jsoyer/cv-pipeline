FROM texlive/texlive:latest

# Install Python runtime
RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        python3 python3-pip python3-venv \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

# Install Python dependencies (separate layer for caching)
COPY requirements.txt .
RUN pip3 install --break-system-packages --no-cache-dir -r requirements.txt

# Copy the tool (no personal data)
COPY awesome-cv/ awesome-cv/
COPY scripts/ scripts/
COPY Makefile .

# Patch font name if TeX Live has renamed SourceSansPro → SourceSans3
RUN if ! fc-list | grep -qi "SourceSansPro"; then \
        sed -i 's/SourceSansPro/SourceSans3/g' awesome-cv/awesome-cv.cls; \
    fi

ENV TEXINPUTS=/workspace/awesome-cv:

# Mount your data/ directory at runtime:
#   docker run --rm -v $(pwd)/data:/workspace/data ghcr.io/jsoyer/cv-pipeline make render
VOLUME ["/workspace/data"]

CMD ["make", "help"]
