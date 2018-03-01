#!/usr/bin/env python
import time
from random import randint

megabyte = (0,) * (1024 * 1024 / 8)

def predefinedSequence():
	while True:
		print "Now in 7G"
		data = 7000 * megabyte
		time.sleep(120)
		
		print "Now in 5G"
		data = 5000 * megabyte
		time.sleep(200)
		
		print "Now in 3G"
		data = 3000 * megabyte
		time.sleep(100)
		
		print "Now in 4.5G"
		data = 4500 * megabyte
		time.sleep(200)
		
		print "Now in 6G"
		data = 6000 * megabyte
		time.sleep(360)
		
		print "Now in 0G"
		data = 1 * megabyte
		time.sleep(200)

def randomSequence():
	try:
		while True:
			wait = random.randint(120,500)
			size = random.randint(100,8192)
			print "Going to hog " + str(size) + " for " + str(wait) + " seconds."
			data = size * megabyte
			time.sleep(wait)
	except KeyboardInterrupt:
		exit(0)

randomSequence()
