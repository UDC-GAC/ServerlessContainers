from eve import Eve

eve_rest = Eve(settings='settings.py')

if __name__ == '__main__':
	eve_rest.run(host='0.0.0.0')
