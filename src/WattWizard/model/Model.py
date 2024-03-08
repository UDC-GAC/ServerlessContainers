class Model(object):

    model_vars = None
    times_trained = None
    pretrained = None
    idle_consumption = None

    def __init__(self):
        self.model_vars = []
        self.times_trained = 0
        self.pretrained = False
        self.idle_consumption = 0
        
    def get_coefs(self):
        return self.model.coef_.tolist() if self.pretrained or self.times_trained > 0 else None

    def get_intercept(self):
        return self.model.intercept_.tolist() if self.pretrained or self.times_trained > 0 else None

    def get_times_trained(self):
        return self.times_trained

    def get_model_vars(self):
        return self.model_vars
    
    def get_idle_consumption(self):
        return self.idle_consumption if self.pretrained else None

    def set_model_vars(self, v):
        self.model_vars = v
    
    def set_idle_consumption(self, v):
        self.idle_consumption = v
    
    def is_fitted(self, attr_name):
        estimator = getattr(self, attr_name, None)
        return hasattr(estimator, 'n_features_in_')
