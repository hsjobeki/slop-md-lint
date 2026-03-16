# Some Feature

This module configures a VPN tunnel between machines. It sets up WireGuard
tunnels — encrypted and authenticated — for all machines in the network.

The configuration is declarative. You add machines to the inventory and
deploy. Keys are generated and distributed automatically via the vars system.

Each machine gets a unique keypair. Public keys are exchanged during deployment
so machines can authenticate each other. No manual key management needed.

Traffic between machines is encrypted end-to-end using WireGuard. The overlay
network runs on top of whatever physical network you have.
