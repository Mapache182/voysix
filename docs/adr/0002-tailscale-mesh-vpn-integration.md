# ADR 0002: Tailscale Mesh-VPN Integration

* Status: Accepted
* Deciders: Antigravity, USER
* Date: 2026-05-14

## Context and Problem Statement

For the Client-Worker split (ADR-001) to work, the desktop client needs to communicate with the remote worker. Traditional methods (static IPs, port forwarding, dynamic DNS) are:
1. Difficult for non-technical users to set up.
2. Insecure if not properly encrypted (TLS/SSL management).
3. Often blocked by NAT or CGNAT (mobile networks, office Wi-Fi).

We need a secure, easy-to-use networking layer that works "out of the box" across different environments.

## Decision Drivers

* **Ease of Use**: Zero-configuration setup for the end-user.
* **Security**: Mandatory encryption of voice data.
* **Reliability**: Connection must work through NAT and firewalls.
* **Discovery**: Ability to find the worker by a human-readable name.

## Considered Options

1. **Direct IP / Port Forwarding**: Users manually enter IPs and configure routers.
2. **Reverse Proxy (Cloud-based)**: Tunnel traffic through a public server (e.g., ngrok, Cloudflare Tunnel).
3. **Mesh-VPN (Tailscale)**: Create a private virtual network between devices.

## Decision Outcome

Chosen option: **Mesh-VPN (Tailscale)**, because it solves both connectivity and security with minimal user friction.

### Implementation Details:
- **Discovery**: The `WorkerClient` uses `tailscale status --json` to resolve the worker's node name into a Tailscale IP (100.x.y.z).
- **Authentication**: Users can provide a Tailscale Auth Key in the app settings, which the app uses to automatically join the Tailnet.
- **Auto-Installation**: The Voysix App includes a `TailscaleManager` that can download and install the Tailscale MSI on Windows if it's missing.
- **Portability**: Tailscale works on Windows, Linux (Docker), and macOS, covering all Voysix target platforms.

### Consequences

* **Good**: No public IPs or open ports required; traffic is end-to-end encrypted.
* **Good**: Works seamlessly on public Wi-Fi and mobile hotspots.
* **Bad**: Adds a dependency on a third-party service (Tailscale).
* **Bad**: Requires the Tailscale daemon to be running on both client and worker.

## Pros and Cons of the Options

### Direct IP
* Good: No third-party dependencies.
* Bad: Extremely high barrier to entry; insecure without manual TLS setup.

### Reverse Proxy
* Good: Easy to set up.
* Bad: Traffic usually passes through the proxy provider's servers in plaintext (unless using complex E2EE).

### Tailscale (Chosen)
* Good: Industry-standard security (WireGuard); bypasses NAT perfectly; built-in discovery.
* Bad: Proprietary control plane (though data plane is open-source WireGuard).
