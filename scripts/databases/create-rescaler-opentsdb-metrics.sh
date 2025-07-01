#!/usr/bin/env bash

METRICS=(
  # LIMITS
  # - CPU
  limit.cpu.lower
  limit.cpu.upper
  limit.cpu.boundary
  # - MEM
  limit.mem.lower
  limit.mem.upper
  limit.mem.boundary
  # - DISK
  #   * READS
  limit.disk_read.lower
  limit.disk_read.upper
  limit.disk_read.boundary
  #   * WRITES
  limit.disk_write.lower
  limit.disk_write.upper
  limit.disk_write.boundary
  # - NET
  limit.net.lower
  limit.net.upper
  limit.net.boundary
  # - ENERGY
  limit.energy.upper
  limit.energy.lower
  # RESOURCES
  # - CPU
  structure.cpu.usage
  structure.cpu.current
  structure.cpu.fixed
  structure.cpu.max
  structure.cpu.min
  # - MEM
  structure.mem.usage
  structure.mem.current
  structure.mem.fixed
  structure.mem.max
  structure.mem.min
  # - DISK
  #structure.disk.usage
  structure.disk.current
  #   * READS
  structure.disk_read.usage
  structure.disk_read.current
  structure.disk_read.fixed
  structure.disk_read.max
  structure.disk_read.min
  #   * WRITES
  structure.disk_write.usage
  structure.disk_write.current
  structure.disk_write.fixed
  structure.disk_write.max
  structure.disk_write.min
  # - NET
  structure.net.usage
  structure.net.current
  structure.net.fixed
  structure.net.max
  structure.net.min
  # - ENERGY
  structure.energy.usage
  structure.energy.current
  structure.energy.shares
  structure.energy.max
  structure.energy.min
  # SERVICES CONFIG
  conf.guardian.window_delay
  conf.guardian.event_timeout
  conf.guardian.window_timelapse
  conf.scaler.request_timeout
  conf.scaler.polling_frequency
  # USER
  user.energy.used
  user.energy.max
  user.cpu.current
  user.cpu.usage
)

./build/tsdb mkmetric "${METRICS[@]}"