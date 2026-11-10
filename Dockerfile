FROM condaforge/miniforge3:latest
USER root
RUN apt-get update && apt-get install -y --no-install-recommends openssh-server iproute2 ca-certificates && rm -rf /var/lib/apt/lists/* /etc/ssh/ssh_host_* && mkdir -p /run/sshd
COPY environment.yml /tmp/environment.yml
RUN conda env create -p /opt/block -f /tmp/environment.yml && conda clean -afy
ENV PATH=/opt/block/bin:$PATH MPLBACKEND=Agg OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=16
WORKDIR /app
COPY block_model.py block_depletion.py plot_block_results.py ./
COPY cases/ cases/
COPY scripts/ scripts/
ENTRYPOINT ["bash","/app/scripts/batch-entrypoint.sh"]
CMD ["smoke"]
