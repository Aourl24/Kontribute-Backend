import os


class Protect:
	def __init__ (self,file=".env"):
		self.values = []

	def read(self):
		directory =os.path.dirname(os.path.abspath(__file__))
		file_path = os.path.join(directory,'.env')
		protected_value = ""
		with open(file_path,'r') as files:
			self.values = [item.strip() for item in files.readlines()]

	def protect(self,variable,file=".env"):
		return self.values[variable]

