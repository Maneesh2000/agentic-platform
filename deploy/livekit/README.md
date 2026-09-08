# Self-hosted LiveKit SFU on Kubernetes

The media plane. Read the root README's ports contract first.

## Hard constraints (accepted up front)

- `hostNetwork: true` → **one SFU pod per node**; scales by adding nodes.
- No service mesh on SFU nodes (the chart disables sidecar injection itself).
- **Not deployable to private or serverless clusters** — extra NAT layers
  break ICE. Nodes need public IPs.

## Install

```bash
helm repo add livekit https://helm.livekit.io
kubectl create namespace livekit

# API keys live in a Secret, never in values files. Generate a pair:
API_KEY="API$(openssl rand -hex 6)"
API_SECRET="$(openssl rand -base64 32)"
kubectl create secret generic livekit-keys -n livekit \
  --from-literal=keys.yaml="${API_KEY}: ${API_SECRET}"

kubectl apply -f redis.yaml          # or point values.yaml at managed Redis
kubectl apply -f turn-cert.yaml      # needs cert-manager + ClusterIssuer

helm install livekit livekit/livekit-server -n livekit -f values.yaml
# dev cluster: add `-f values-dev.yaml`
```

Label the SFU node pool: `livekit.io/pool: sfu`.

## Verify

1. Pods land one-per-node on the sfu pool and register in Redis.
2. From an agent pod: `nc -zv livekit-server.livekit 7880`, then confirm a
   session negotiates media — this is where `advertise_internal_ip` proves out.
3. Browser on an external network: in `chrome://webrtc-internals` the
   selected candidate pair must be **UDP** — TURN relay as the *default*
   path means the 7882-7892/udp range is not actually open.
