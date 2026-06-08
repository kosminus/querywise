# VPC + private-services-access peering so Cloud SQL gets a private IP. Set
# create_network = false to use an existing VPC that already has PSA configured.

resource "google_compute_network" "this" {
  count                   = var.create_network ? 1 : 0
  name                    = "${var.name_prefix}-vpc"
  auto_create_subnetworks = false
}

resource "google_compute_subnetwork" "this" {
  count                    = var.create_network ? 1 : 0
  name                     = "${var.name_prefix}-subnet"
  ip_cidr_range            = var.subnet_cidr
  region                   = var.region
  network                  = google_compute_network.this[0].id
  private_ip_google_access = true
}

# Reserved range + connection for private services access (Cloud SQL, etc.).
resource "google_compute_global_address" "psa" {
  count         = var.create_network ? 1 : 0
  name          = "${var.name_prefix}-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.this[0].id
}

resource "google_service_networking_connection" "psa" {
  count                   = var.create_network ? 1 : 0
  network                 = google_compute_network.this[0].id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.psa[0].name]
}
