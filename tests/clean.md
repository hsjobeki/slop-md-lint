# Networking

Clan machines can form overlay networks for private communication. Traffic
between machines is encrypted end-to-end using WireGuard tunnels.

## How it works

Each machine gets a WireGuard keypair generated via `clan vars`. When you
deploy, the public keys are exchanged automatically and tunnels are configured.

Machines discover each other through a shared coordination endpoint. No manual
IP configuration is needed.

## Configuration

Add the networking module to your inventory:

```nix
inventory.instances = {
  network = {
    module = {
      name = "data-mesher";
      input = "clan-core";
    };
    roles.peer.tags.all = { };
  };
};
```

After deploying, machines can reach each other by hostname over the overlay.

## Troubleshooting

Check if the tunnel is up:

```bash
wg show
```

If a machine can't reach others, verify that its public key was distributed:

```bash
clan vars list my-machine | grep data-mesher
```

The coordination endpoint must be reachable from all machines. If you're behind
NAT, you may need to configure a relay node.
