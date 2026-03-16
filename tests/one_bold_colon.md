# Backup Setup

Configure backups for your machines. The borgbackup module handles encryption,
deduplication, and scheduling.

Two roles are available:

- **Client**: machines that create and send backups to a server.
- Server: machines that receive and store backups.

Add the module to your inventory and assign roles. Clients need a destination
configured, servers just need to be reachable. Keys are managed automatically.

Backups run on the schedule you configure. The default is daily. You can
check backup status with `clan backups list`.
