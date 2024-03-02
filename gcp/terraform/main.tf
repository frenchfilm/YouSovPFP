terraform {
  backend "gcs" {
    bucket = "esov-api-terraformstate"
    prefix = "esov-terraformstate"
  }
}

variable "projectId" {
  type = string
}

variable "publicImagesBucketName" {
  type = string
}

variable "argsImagesBucketName" {
  type = string
}

provider "google" {
  project = var.projectId
}

resource "google_storage_bucket" "public_images_bucket" {
  name     = var.publicImagesBucketName
  # enable public access to the bucket
  uniform_bucket_level_access = true
  location = "US"
}

resource "google_storage_bucket_iam_member" "member_public_images_bucket" {
  bucket = var.publicImagesBucketName
  role   = "roles/storage.objectViewer"
  member = "allUsers"
  depends_on = [ google_storage_bucket.public_images_bucket ]
}

resource "google_storage_bucket" "images_args_bucket" {
  name     = var.argsImagesBucketName
  # enable public access to the bucket
  uniform_bucket_level_access = true
  location = "US"
}

resource "google_storage_bucket_iam_member" "member_images_args_bucket" {
  bucket = var.argsImagesBucketName
  role   = "roles/storage.objectViewer"
  member = "allUsers"
  depends_on = [ google_storage_bucket.images_args_bucket ]
}